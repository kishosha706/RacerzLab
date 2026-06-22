from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _package_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_ui_typecheck_script_exists() -> None:
    scripts = _package_json("ui/package.json")["scripts"]

    assert scripts["typecheck"] == "tsc --noEmit"


def test_root_ui_typecheck_script_exists() -> None:
    scripts = _package_json("package.json")["scripts"]

    assert scripts["typecheck:ui"] == "cd ui && npm run typecheck"
