from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from racelab_engine.models.racelab_session import RaceLabSession
from racelab_engine.storage.db import initialize_database


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _load_json(value: str | None, fallback: Any = None) -> Any:
    return json.loads(value) if value else fallback


def _ensure_schema(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS racelab_sessions (
            session_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            track_name TEXT,
            car_name TEXT,
            run_ids_json TEXT DEFAULT '[]',
            last_opened_run_id TEXT,
            last_selected_lap INTEGER,
            last_workspace TEXT,
            notebook_finding_ids_json TEXT DEFAULT '[]',
            status TEXT DEFAULT 'active'
        )
    """)


def create_session(name: str | None = None, db_path: str | Path | None = None) -> RaceLabSession:
    session_id = f"session_{uuid.uuid4().hex[:12]}"
    now = _utc_now()
    effective_name = name or f"Session {now[:10]}"

    conn = initialize_database(db_path)
    _ensure_schema(conn)
    with conn:
        conn.execute(
            """
            INSERT INTO racelab_sessions (
                session_id, name, created_at, updated_at, status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, effective_name, now, now, "active"),
        )
    conn.close()

    return RaceLabSession(
        session_id=session_id,
        name=effective_name,
        created_at=now,
        updated_at=now,
        status="active",
    )


def _row_to_session(row: dict[str, Any]) -> RaceLabSession:
    return RaceLabSession(
        session_id=row["session_id"],
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        track_name=row.get("track_name"),
        car_name=row.get("car_name"),
        run_ids=_load_json(row.get("run_ids_json"), []),
        last_opened_run_id=row.get("last_opened_run_id"),
        last_selected_lap=row.get("last_selected_lap"),
        last_workspace=row.get("last_workspace"),
        notebook_finding_ids=_load_json(row.get("notebook_finding_ids_json"), []),
        status=row.get("status", "active"),
    )


def list_sessions(include_archived: bool = False, db_path: str | Path | None = None) -> list[RaceLabSession]:
    conn = initialize_database(db_path)
    _ensure_schema(conn)
    sql = "SELECT * FROM racelab_sessions"
    if not include_archived:
        sql += " WHERE status = 'active'"
    sql += " ORDER BY updated_at DESC"
    rows = conn.execute(sql).fetchall()
    conn.close()
    return [_row_to_session(dict(r)) for r in rows]


def get_session(session_id: str, db_path: str | Path | None = None) -> RaceLabSession | None:
    conn = initialize_database(db_path)
    _ensure_schema(conn)
    row = conn.execute("SELECT * FROM racelab_sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    return _row_to_session(dict(row)) if row else None


def update_session(
    session_id: str,
    *,
    name: str | None = None,
    track_name: str | None = None,
    car_name: str | None = None,
    last_opened_run_id: str | None = None,
    last_selected_lap: int | None = None,
    last_workspace: str | None = None,
    status: str | None = None,
    db_path: str | Path | None = None,
) -> RaceLabSession | None:
    conn = initialize_database(db_path)
    _ensure_schema(conn)
    now = _utc_now()
    updates: list[str] = ["updated_at = ?"]
    params: list[Any] = [now]
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if track_name is not None:
        updates.append("track_name = ?")
        params.append(track_name)
    if car_name is not None:
        updates.append("car_name = ?")
        params.append(car_name)
    if last_opened_run_id is not None:
        updates.append("last_opened_run_id = ?")
        params.append(last_opened_run_id)
    if last_selected_lap is not None:
        updates.append("last_selected_lap = ?")
        params.append(last_selected_lap)
    if last_workspace is not None:
        updates.append("last_workspace = ?")
        params.append(last_workspace)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    params.append(session_id)
    conn.execute(f"UPDATE racelab_sessions SET {', '.join(updates)} WHERE session_id = ?", params)
    conn.commit()
    conn.close()
    return get_session(session_id, db_path)


def delete_session(session_id: str, db_path: str | Path | None = None) -> bool:
    """Delete a RaceLab session. Does NOT delete imported telemetry files."""
    conn = initialize_database(db_path)
    _ensure_schema(conn)
    cursor = conn.execute("DELETE FROM racelab_sessions WHERE session_id = ?", (session_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def archive_session(session_id: str, db_path: str | Path | None = None) -> RaceLabSession | None:
    return update_session(session_id, status="archived", db_path=db_path)


def add_run_to_session(session_id: str, run_id: str, db_path: str | Path | None = None) -> RaceLabSession | None:
    session = get_session(session_id, db_path)
    if not session:
        return None
    if run_id in session.run_ids:
        return session
    new_run_ids = session.run_ids + [run_id]
    conn = initialize_database(db_path)
    _ensure_schema(conn)
    now = _utc_now()
    conn.execute(
        "UPDATE racelab_sessions SET run_ids_json = ?, updated_at = ? WHERE session_id = ?",
        (_json(new_run_ids), now, session_id),
    )
    conn.commit()
    conn.close()
    return get_session(session_id, db_path)


def remove_run_from_session(session_id: str, run_id: str, db_path: str | Path | None = None) -> RaceLabSession | None:
    session = get_session(session_id, db_path)
    if not session:
        return None
    new_run_ids = [r for r in session.run_ids if r != run_id]
    conn = initialize_database(db_path)
    _ensure_schema(conn)
    now = _utc_now()
    conn.execute(
        "UPDATE racelab_sessions SET run_ids_json = ?, updated_at = ? WHERE session_id = ?",
        (_json(new_run_ids), now, session_id),
    )
    conn.commit()
    conn.close()
    return get_session(session_id, db_path)


def set_last_opened(
    session_id: str,
    run_id: str | None,
    lap: int | None = None,
    workspace: str | None = None,
    db_path: str | Path | None = None,
) -> RaceLabSession | None:
    return update_session(
        session_id,
        last_opened_run_id=run_id,
        last_selected_lap=lap,
        last_workspace=workspace,
        db_path=db_path,
    )
