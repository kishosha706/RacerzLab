from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from racelab_engine.services.session_service import (  # noqa: E402
    create_session,
    delete_session,
    get_session,
)


_SMOKE_NAME_PREFIX = "RacerZLab packaged restart smoke "


def _database_path(raw: str) -> Path:
    path = Path(raw).resolve(strict=True)
    if not path.is_file() or path.name != "racelab.sqlite":
        raise ValueError("the packaged smoke database must be an existing racelab.sqlite file")
    return path


def _smoke_name(raw: str) -> str:
    if not raw.startswith(_SMOKE_NAME_PREFIX) or len(raw) <= len(_SMOKE_NAME_PREFIX):
        raise ValueError("the session name is not a packaged-smoke identity")
    return raw


def _seed(database: Path, name: str) -> dict[str, object]:
    session = create_session(name=name, db_path=database)
    return {
        "session_id": session.session_id,
        "name": session.name,
        "status": session.status,
    }


def _verify(database: Path, session_id: str, name: str) -> dict[str, object]:
    session = get_session(session_id, db_path=database)
    if session is None or session.name != name or session.status != "active":
        raise RuntimeError("the packaged-smoke session marker is absent or identity-mismatched")
    return {
        "present": True,
        "session_id": session.session_id,
        "name": session.name,
        "status": session.status,
    }


def _delete(database: Path, session_id: str, name: str) -> dict[str, object]:
    session = get_session(session_id, db_path=database)
    if session is None:
        return {"deleted": False, "already_absent": True, "session_id": session_id}
    if session.name != name:
        raise RuntimeError("refusing to delete a session that is not the exact smoke marker")
    return {
        "deleted": delete_session(session_id, db_path=database),
        "already_absent": False,
        "session_id": session_id,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Seed and verify one API-visible session for the packaged restart smoke."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed = subparsers.add_parser("seed")
    seed.add_argument("--database", required=True)
    seed.add_argument("--name", required=True)

    for command in ("verify", "delete"):
        child = subparsers.add_parser(command)
        child.add_argument("--database", required=True)
        child.add_argument("--session-id", required=True)
        child.add_argument("--name", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    database = _database_path(args.database)
    name = _smoke_name(args.name)
    if args.command == "seed":
        result = _seed(database, name)
    elif args.command == "verify":
        result = _verify(database, args.session_id, name)
    else:
        result = _delete(database, args.session_id, name)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
