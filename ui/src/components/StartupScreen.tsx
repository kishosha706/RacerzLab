import { Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { createSession, deleteSession, fetchSessions } from "../api/client";
import type { RaceLabSession } from "../types/session";

type StartupScreenProps = {
  onSessionSelected: (sessionId: string) => void;
};

export function StartupScreen({ onSessionSelected }: StartupScreenProps) {
  const [sessions, setSessions] = useState<RaceLabSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchSessions();
      setSessions(data);
    } catch { setSessions([]); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void loadSessions(); }, [loadSessions]);

  const handleNewSession = useCallback(async () => {
    setCreating(true);
    try {
      const session = await createSession();
      onSessionSelected(session.session_id);
    } catch { /* empty */ }
    finally { setCreating(false); }
  }, [onSessionSelected]);

  const handleDelete = useCallback(async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      setConfirmDelete(null);
      void loadSessions();
    } catch { /* empty */ }
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

        <p className="start-hint">Open a previous session below.</p>
      </div>

      {loading && <p className="muted" style={{ textAlign: "center", marginTop: 32 }}>Loading sessions…</p>}

      {!loading && sessions.length === 0 && (
        <div className="start-empty">
          <p className="muted">No previous sessions yet.</p>
          <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>Create a new session to import your first telemetry file.</p>
        </div>
      )}

      {!loading && sessions.length > 0 && (
        <section className="session-list">
          <h2 className="session-list-heading">Previous Sessions</h2>
          <div className="session-list-grid">
            {sessions.map((s) => (
              <div key={s.session_id} className="session-card">
                <button
                  className="session-card-body"
                  onClick={() => onSessionSelected(s.session_id)}
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
