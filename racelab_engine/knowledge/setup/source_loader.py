from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
DOC_SOURCE = REPO_ROOT / "docs" / "setup_knowledge" / "racerzlab_master_setup_matrix.md"
LOCAL_SOURCE_COPY = REPO_ROOT / "data" / "knowledge" / "source_guides" / "racerzlab_master_setup_matrix.md"


@dataclass(frozen=True)
class SourceGuide:
    source_id: str
    path: Path
    text: str


def resolve_master_setup_matrix() -> Path:
    if DOC_SOURCE.exists():
        return DOC_SOURCE
    if LOCAL_SOURCE_COPY.exists():
        return LOCAL_SOURCE_COPY
    raise FileNotFoundError(
        "Missing master setup matrix. Expected docs/setup_knowledge/racerzlab_master_setup_matrix.md "
        "or data/knowledge/source_guides/racerzlab_master_setup_matrix.md"
    )


def load_master_setup_matrix() -> SourceGuide:
    path = resolve_master_setup_matrix()
    return SourceGuide(
        source_id="racerzlab_master_setup_matrix_v1",
        path=path,
        text=path.read_text(encoding="utf-8"),
    )
