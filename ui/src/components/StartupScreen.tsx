import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  Gauge,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { createSession, deleteSession, fetchSessions } from "../api/client";
import racerzlabBanner from "../assets/racerzlab-banner-1920.jpg";
import type { RaceLabSession, SessionSelectionSource } from "../types/session";
import { isBrowser } from "../utils/env";

type StartupScreenProps = {
  onSessionSelected: (sessionId: string, source: SessionSelectionSource) => void;
};

type PendingStartupFocus =
  | { kind: "delete-trigger"; sessionId: string }
  | { kind: "session-or-new"; preferredSessionIds: string[]; fallbackIndex: number };

function sessionAccessibleContext(session: RaceLabSession): string {
  const runCount = `${session.run_ids.length} recorded run${session.run_ids.length === 1 ? "" : "s"}`;
  return `${session.name}, ${session.track_name ?? "track not labeled"}, ${session.car_name ?? "car not labeled"}, ${runCount}`;
}

function neighboringSessionIds(sessions: RaceLabSession[], sessionId: string): string[] {
  const deletedIndex = sessions.findIndex((session) => session.session_id === sessionId);
  if (deletedIndex < 0) {
    return sessions
      .filter((session) => session.session_id !== sessionId)
      .map((session) => session.session_id);
  }

  const neighbors: string[] = [];
  for (let distance = 1; distance < sessions.length; distance += 1) {
    const next = sessions[deletedIndex + distance];
    const previous = sessions[deletedIndex - distance];
    if (next) neighbors.push(next.session_id);
    if (previous) neighbors.push(previous.session_id);
  }
  return neighbors;
}

export function StartupScreen({ onSessionSelected }: StartupScreenProps) {
  const browser = isBrowser();
  const [sessions, setSessions] = useState<RaceLabSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deletingSession, setDeletingSession] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [bannerVisible, setBannerVisible] = useState(true);
  const [launchSplashVisible, setLaunchSplashVisible] = useState(true);

  const loadRequestRef = useRef(0);
  const deletingSessionRef = useRef<string | null>(null);
  const pendingFocusRef = useRef<PendingStartupFocus | null>(null);
  const newSessionButtonRef = useRef<HTMLButtonElement | null>(null);
  const sessionCardRefs = useRef(new Map<string, HTMLButtonElement>());
  const deleteTriggerRefs = useRef(new Map<string, HTMLButtonElement>());
  const keepButtonRefs = useRef(new Map<string, HTMLButtonElement>());

  const loadSessions = useCallback(async () => {
    const requestId = loadRequestRef.current + 1;
    loadRequestRef.current = requestId;
    setLoading(true);
    setLoadError(null);
    try {
      const data = await fetchSessions();
      if (requestId !== loadRequestRef.current) return null;
      setSessions(data);
      return data;
    } catch (err) {
      if (requestId !== loadRequestRef.current) return null;
      setSessions([]);
      setLoadError(err instanceof Error ? err.message : "Could not load previous sessions.");
      return null;
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => { void loadSessions(); }, [loadSessions]);

  useEffect(() => {
    if (!confirmDelete || deletingSession) return;
    const keepButton = keepButtonRefs.current.get(confirmDelete);
    if (keepButton?.isConnected) keepButton.focus();
  }, [confirmDelete, deletingSession]);

  useEffect(() => {
    const pendingFocus = pendingFocusRef.current;
    if (!pendingFocus || loading || confirmDelete) return;

    let target: HTMLButtonElement | null | undefined;
    if (pendingFocus.kind === "delete-trigger") {
      target = deleteTriggerRefs.current.get(pendingFocus.sessionId);
    } else {
      target = pendingFocus.preferredSessionIds
        .map((sessionId) => sessionCardRefs.current.get(sessionId))
        .find((candidate) => candidate?.isConnected);

      if (!target && sessions.length > 0) {
        const fallbackIndex = Math.min(
          Math.max(pendingFocus.fallbackIndex, 0),
          sessions.length - 1,
        );
        target = sessionCardRefs.current.get(sessions[fallbackIndex].session_id)
          ?? sessions
            .map((session) => sessionCardRefs.current.get(session.session_id))
            .find((candidate) => candidate?.isConnected);
      }
      target ??= newSessionButtonRef.current;
    }

    if (!target?.isConnected || target.disabled) return;
    target.focus();
    if (document.activeElement === target) pendingFocusRef.current = null;
  }, [confirmDelete, creating, loading, sessions]);

  const enterSessionPicker = useCallback(() => {
    setLaunchSplashVisible(false);
  }, []);

  useEffect(() => {
    if (!launchSplashVisible) return undefined;

    const handleLaunchKey = (event: KeyboardEvent) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        enterSessionPicker();
      }
    };

    window.addEventListener("keydown", handleLaunchKey);
    return () => window.removeEventListener("keydown", handleLaunchKey);
  }, [enterSessionPicker, launchSplashVisible]);

  const handleNewSession = useCallback(async () => {
    setCreating(true);
    setCreateError(null);
    try {
      const session = await createSession();
      onSessionSelected(session.session_id, "new");
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Could not create session.");
    } finally {
      setCreating(false);
    }
  }, [onSessionSelected]);

  const handleRequestDelete = useCallback((sessionId: string) => {
    if (deletingSessionRef.current) return;
    setDeleteError(null);
    setConfirmDelete(sessionId);
  }, []);

  const handleKeepSession = useCallback((sessionId: string) => {
    if (deletingSessionRef.current) return;
    setDeleteError(null);
    pendingFocusRef.current = { kind: "delete-trigger", sessionId };
    setConfirmDelete(null);
  }, []);

  const handleDelete = useCallback(async (sessionId: string) => {
    if (deletingSessionRef.current) return;
    const deletedIndex = sessions.findIndex((session) => session.session_id === sessionId);
    const preferredSessionIds = neighboringSessionIds(sessions, sessionId);
    deletingSessionRef.current = sessionId;
    setDeletingSession(sessionId);
    setDeleteError(null);
    try {
      await deleteSession(sessionId);
      await loadSessions();
      pendingFocusRef.current = {
        kind: "session-or-new",
        preferredSessionIds,
        fallbackIndex: deletedIndex < 0 ? 0 : deletedIndex,
      };
      setConfirmDelete(null);
    } catch {
      // Keep confirmation open. Clearing the busy state returns focus to the safe action.
      setDeleteError("Could not remove this session. Nothing was deleted. Try again or keep it.");
    } finally {
      deletingSessionRef.current = null;
      setDeletingSession(null);
    }
  }, [loadSessions, sessions]);

  return (
    <main className="start-shell" data-banner-visible={bannerVisible} data-launch-splash={launchSplashVisible}>
      {bannerVisible && (
        <img
          className="startup-bg-image"
          src={racerzlabBanner}
          alt=""
          aria-hidden="true"
          onError={() => setBannerVisible(false)}
        />
      )}
      <div className="startup-bg-vignette" aria-hidden="true" />

      {launchSplashVisible ? (
        <button
          type="button"
          className="launch-splash-gate"
          onClick={enterSessionPicker}
          aria-label="Enter RacerZLab garage"
        >
          <span className="startup-kicker">Local race engineering</span>
          <span className="launch-splash-meta">Turn telemetry into one trustworthy next move.</span>
          <span className="launch-splash-prompt">Enter the garage <ArrowRight size={16} aria-hidden="true" /></span>
        </button>
      ) : (
      <div className="startup-content">
        <div className="start-hero">
          <div className="start-launch-panel">
            <span className="startup-kicker">Evidence-first workspace</span>
            <h1 className="start-title">Pick up the engineering thread</h1>
            <p className="start-subtitle">
              Qualify the run, find the repeatable loss, and leave with one controlled next move.
            </p>

            <div className="startup-value-grid" aria-label="RacerZLab engineering workflow">
              <div className="startup-value-item">
                <ShieldCheck size={16} aria-hidden="true" />
                <span><strong>Qualify</strong><small>Reject junk laps and weak evidence</small></span>
              </div>
              <div className="startup-value-item">
                <Gauge size={16} aria-hidden="true" />
                <span><strong>Diagnose</strong><small>Find repeatable loss by position</small></span>
              </div>
              <div className="startup-value-item">
                <BrainCircuit size={16} aria-hidden="true" />
                <span><strong>Test</strong><small>Change one thing and verify it</small></span>
              </div>
            </div>

            <div className="start-actions">
              <button
                ref={newSessionButtonRef}
                className="start-primary-btn"
                onClick={handleNewSession}
                disabled={creating}
              >
                <Plus size={18} aria-hidden="true" /> {creating ? "Creating…" : "New engineering session"}
              </button>
            </div>
            <p className="start-primary-note">Runs, setups, reports, and learning stay on this machine.</p>

            {createError && (
              <div className="start-error" style={{ marginTop: 12 }}>
                <p className="error-text" style={{ fontSize: 12, margin: 0 }}>
                  <AlertTriangle size={12} /> {createError}
                </p>
              </div>
            )}

            <p className="start-hint">Or continue a recent engineering session.</p>
          </div>
        </div>

      {loading && <p className="muted" style={{ textAlign: "center", marginTop: 32 }}>Loading sessions…</p>}

      {loadError && !loading && (
        <div className="start-empty" style={{ marginTop: 32 }}>
          <p className="error-text" style={{ fontSize: 12, margin: 0 }}>
            <AlertTriangle size={12} /> {loadError}
          </p>
          {browser && (
            <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
              Start backend: <code style={{ color: "#38bdf8", fontSize: 11 }}>python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8010</code>
            </p>
          )}
          <button className="trackmap-action-btn" onClick={loadSessions} style={{ marginTop: 8 }}>
            <RefreshCw size={12} /> Retry
          </button>
        </div>
      )}

      {!loading && !loadError && sessions.length === 0 && (
        <div className="start-empty">
          <p className="muted">No previous sessions yet.</p>
          <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>Create a new session to import your first telemetry file.</p>
        </div>
      )}

      {!loading && !loadError && sessions.length > 0 && (
        <section className="session-list">
          <h2 className="session-list-heading">Continue engineering</h2>
          {deleteError && <p className="session-delete-error" role="alert">{deleteError}</p>}
          <div className="session-list-grid">
            {sessions.map((s) => (
              <div key={s.session_id} className="session-card">
                <button
                  ref={(node) => {
                    if (node) sessionCardRefs.current.set(s.session_id, node);
                    else sessionCardRefs.current.delete(s.session_id);
                  }}
                  className="session-card-body"
                  onClick={() => onSessionSelected(s.session_id, "existing")}
                  aria-label={`Open session ${sessionAccessibleContext(s)}`}
                >
                  <span className="session-card-overline">
                    {s.run_ids.length > 0
                      ? `${s.run_ids.length} recorded run${s.run_ids.length === 1 ? "" : "s"}`
                      : "Ready for first import"}
                  </span>
                  <span className="session-card-title">{s.name}</span>
                  <span className="session-card-meta">
                    <span>{s.track_name ?? "Track not labeled"}</span>
                    <span className="session-card-sep">·</span>
                    <span>{s.car_name ?? "Car not labeled"}</span>
                    {s.run_ids.length > 0 && (
                      <>
                        <span className="session-card-sep">·</span>
                        <span>{s.run_ids.length} run{s.run_ids.length !== 1 ? "s" : ""}</span>
                      </>
                    )}
                  </span>
                  <span className="session-card-footer">
                    <span className="session-card-date">Updated {s.updated_at?.slice(0, 10) ?? "recently"}</span>
                    <span className="session-card-continue">Continue <ArrowRight size={13} aria-hidden="true" /></span>
                  </span>
                </button>
                <div className="session-card-actions">
                  {confirmDelete === s.session_id ? (
                    <div className="session-confirm-delete">
                      <span className="muted" style={{ fontSize: 11 }}>Remove session?</span>
                      <button
                        className="session-delete-confirm-btn"
                        onClick={() => handleDelete(s.session_id)}
                        aria-label={`Remove session ${sessionAccessibleContext(s)}`}
                        disabled={deletingSession === s.session_id}
                      >{deletingSession === s.session_id ? "Removing…" : "Remove"}</button>
                      <button
                        ref={(node) => {
                          if (node) keepButtonRefs.current.set(s.session_id, node);
                          else keepButtonRefs.current.delete(s.session_id);
                        }}
                        className="session-delete-cancel-btn"
                        onClick={() => handleKeepSession(s.session_id)}
                        aria-label={`Keep session ${sessionAccessibleContext(s)}`}
                        disabled={deletingSession === s.session_id}
                      >Keep</button>
                    </div>
                  ) : (
                    <button
                      ref={(node) => {
                        if (node) deleteTriggerRefs.current.set(s.session_id, node);
                        else deleteTriggerRefs.current.delete(s.session_id);
                      }}
                      className="session-delete-btn"
                      onClick={() => handleRequestDelete(s.session_id)}
                      aria-label={`Delete session ${sessionAccessibleContext(s)}`}
                      title="Delete session"
                      disabled={deletingSession !== null}
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      </div>
      )}
    </main>
  );
}
