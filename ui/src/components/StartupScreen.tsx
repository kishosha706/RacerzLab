import { AlertTriangle, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { createSession, deleteSession, fetchSessions } from "../api/client";
import type { RaceLabSession, SessionSelectionSource } from "../types/session";

type StartupScreenProps = {
  onSessionSelected: (sessionId: string, source: SessionSelectionSource) => void;
};

export function StartupScreen({ onSessionSelected }: StartupScreenProps) {
  const [sessions, setSessions] = useState<RaceLabSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await fetchSessions();
      setSessions(data);
    } catch (err) {
      setSessions([]);
      setLoadError(err instanceof Error ? err.message : "Could not load previous sessions.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadSessions(); }, [loadSessions]);

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

  const handleDelete = useCallback(async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      setConfirmDelete(null);
      void loadSessions();
    } catch { /* delete failure is non-critical */ }
  }, [loadSessions]);

  return (
    <main className="start-shell">
      <div className="start-hero">
        <span className="start-eyebrow">RACERZLAB</span>
        <h1 className="start-title">Start a new RacerZLab session</h1>
        <p className="start-subtitle">
          Import telemetry, inspect evidence, compare setup changes, and build your next test plan.
        </p>

        <div className="start-actions">
          <button className="start-primary-btn" onClick={handleNewSession} disabled={creating}>
            <Plus size={18} /> {creating ? "Creating…" : "New Session"}
          </button>
        </div>

        {createError && (
          <div className="start-error" style={{ marginTop: 12 }}>
            <p className="error-text" style={{ fontSize: 12, margin: 0 }}>
              <AlertTriangle size={12} /> {createError}
            </p>
          </div>
        )}

        <p className="start-hint">Open a previous session below.</p>
      </div>

      {loading && <p className="muted" style={{ textAlign: "center", marginTop: 32 }}>Loading sessions…</p>}

      {loadError && !loading && (
        <div className="start-empty" style={{ marginTop: 32 }}>
          <p className="error-text" style={{ fontSize: 12, margin: 0 }}>
            <AlertTriangle size={12} /> {loadError}
          </p>
          <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            Start backend: <code style={{ color: "#38bdf8", fontSize: 11 }}>python -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8010</code>
          </p>
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
          <h2 className="session-list-heading">Previous Sessions</h2>
          <div className="session-list-grid">
            {sessions.map((s) => (
              <div key={s.session_id} className="session-card">
                <button
                  className="session-card-body"
                  onClick={() => onSessionSelected(s.session_id, "existing")}
                  aria-label={`Open session ${s.name}`}
                >
                  <span className="session-card-title">{s.name}</span>
                  <span className="session-card-meta">
                    <span>{s.track_name ?? "No track"}</span>
                    <span className="session-card-sep">·</span>
                    <span>{s.car_name ?? "No car"}</span>
                    {s.run_ids.length > 0 && (
                      <>
                        <span className="session-card-sep">·</span>
                        <span>{s.run_ids.length} run{s.run_ids.length !== 1 ? "s" : ""}</span>
                      </>
                    )}
                  </span>
                  <span className="session-card-date">{s.updated_at?.slice(0, 10) ?? ""}</span>
                </button>
                <div className="session-card-actions">
                  {confirmDelete === s.session_id ? (
                    <div className="session-confirm-delete">
                      <span className="muted" style={{ fontSize: 11 }}>Remove session?</span>
                      <button className="session-delete-confirm-btn" onClick={() => handleDelete(s.session_id)}>Remove</button>
                      <button className="session-delete-cancel-btn" onClick={() => setConfirmDelete(null)}>Keep</button>
                    </div>
                  ) : (
                    <button
                      className="session-delete-btn"
                      onClick={() => setConfirmDelete(s.session_id)}
                      aria-label={`Delete session ${s.name}`}
                      title="Delete session"
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
    </main>
  );
}
