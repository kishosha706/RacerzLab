from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel


class FileFingerprint(BaseModel):
    path: str
    file_size: int
    sha256: str
    modified_time: datetime


def fingerprint_file(path: str | Path, chunk_size: int = 1024 * 1024) -> FileFingerprint:
    import hashlib

    file_path = Path(path)
    stat = file_path.stat()
    digest = hashlib.sha256()

    with file_path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(chunk_size), b""):
            digest.update(chunk)

    return FileFingerprint(
        path=str(file_path),
        file_size=stat.st_size,
        sha256=digest.hexdigest(),
        modified_time=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
    )
