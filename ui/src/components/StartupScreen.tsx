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
    <main className="startup-screen">
      <div className="startup-panel">
        <span className="eyebrow">RaceLab Garage</span>
        <h1>Start a new RaceLab session or open a previous session.</h1>

        <button className="primary-button" onClick={handleNewSession} disabled={creating} style={{ marginBottom: 24 }}>
          <Plus size={16} /> {creating ? "Creating…" : "New Session"}
        </button>

        {loading && <p className="muted">Loading previous sessions…</p>}

        {!loading && sessions.length === 0 && (
          <div className="startup-empty">
            <p className="muted">No previous sessions. Create a new session to begin.</p>
          </div>
        )}

        {sessions.length > 0 && (
          <div className="startup-session-list">
            <h3>Previous Sessions</h3>
            {sessions.map((s) => (
              <div key={s.session_id} className="startup-session-row">
                <button className="startup-session-button" onClick={() => onSessionSelected(s.session_id)}>
                  <span className="startup-session-name">{s.name}</span>
                  <span className="startup-session-meta">
                    {s.track_name ?? "No track"} · {s.car_name ?? "No car"}
                    {s.run_ids.length > 0 && ` · ${s.run_ids.length} run(s)`}
                  </span>
                  <span className="startup-session-date">{s.updated_at?.slice(0, 10)}</span>
                </button>
                <div className="startup-session-actions">
                  {confirmDelete === s.session_id ? (
                    <div className="confirm-delete-row">
                      <span className="muted">Remove session? Telemetry files stay.</span>
                      <button className="danger-button" onClick={() => handleDelete(s.session_id)}>Remove</button>
                      <button className="secondary-button" onClick={() => setConfirmDelete(null)}>Cancel</button>
                    </div>
                  ) : (
                    <button className="icon-button" onClick={() => setConfirmDelete(s.session_id)} title="Remove session">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
