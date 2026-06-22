from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import cast

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
import pytest

from api.main import app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_backend_cors_is_local_only() -> None:
    cors = next(middleware for middleware in app.user_middleware if middleware.cls is CORSMiddleware)
    raw_origins = cors.kwargs.get("allow_origins")
    origins: list[str] = cast("list[str]", raw_origins)

    assert "*" not in origins
    assert set(origins) == {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    }

    assert cors.kwargs.get("allow_methods") == ["*"]
    assert cors.kwargs.get("allow_headers") == ["*"]


def test_backend_cors_preflight_accepts_import_headers() -> None:
    response = TestClient(app).options(
        "/api/imports/ibt",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-racerzlab-request-id",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_json_import_routes_reject_malformed_json_cleanly() -> None:
    client = TestClient(app)

    for route in ("/api/imports/ibt", "/api/imports/mt2"):
        response = client.post(
            route,
            content="{not-json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Malformed JSON body."


def test_mt2_json_path_import_passes_path_object(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    mt2_path = tmp_path / "test map.mt2"
    mt2_path.write_bytes(b"placeholder")
    seen: dict[str, object] = {}

    def fake_import(path: Path) -> dict:
        seen["path"] = path
        return {"map_id": "map-1", "status": "parsed"}

    monkeypatch.setattr("racelab_engine.services.track_map_service.import_mt2_file", fake_import)

    response = TestClient(app).post(
        "/api/imports/mt2",
        json={"path": str(mt2_path)},
    )

    assert response.status_code == 200
    assert response.json()["map_id"] == "map-1"
    assert seen["path"] == mt2_path.resolve()


def test_backend_scripts_bind_to_loopback_only() -> None:
    for relative_path in ("scripts/start_api.ps1", "scripts/start_desktop.ps1", "package.json", "api/server.py", "ui/src-tauri/src/lib.rs"):
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "0.0.0.0" not in text

    start_api = (PROJECT_ROOT / "scripts/start_api.ps1").read_text(encoding="utf-8")
    start_desktop = (PROJECT_ROOT / "scripts/start_desktop.ps1").read_text(encoding="utf-8")
    server = (PROJECT_ROOT / "api/server.py").read_text(encoding="utf-8")
    shell = (PROJECT_ROOT / "ui/src-tauri/src/lib.rs").read_text(encoding="utf-8")
    assert "--host 127.0.0.1" in start_api
    assert '"127.0.0.1"' in start_desktop
    assert 'HOST = "127.0.0.1"' in server
    assert 'const BACKEND_HOST: &str = "127.0.0.1";' in shell


def test_packaged_backend_entrypoint_is_production_safe() -> None:
    server = (PROJECT_ROOT / "api/server.py").read_text(encoding="utf-8")
    script = (PROJECT_ROOT / "scripts/build_backend_sidecar.ps1").read_text(encoding="utf-8")
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()

    assert "reload=False" in server
    assert "--reload" not in server
    assert "pyinstaller" in pyproject
    assert "--noconsole" in script
    assert "--onefile" in script
    assert "racerzlab-backend" in script
    assert "ui\\src-tauri\\bin" in script


def test_tauri_shell_starts_hidden_backend_sidecar_and_cleans_up() -> None:
    shell = (PROJECT_ROOT / "ui/src-tauri/src/lib.rs").read_text(encoding="utf-8")

    assert 'const BACKEND_EXE: &str = "racerzlab-backend.exe";' in shell
    assert "CREATE_NO_WINDOW" in shell
    assert ".stdout(Stdio::null())" in shell
    assert ".stderr(Stdio::null())" in shell
    assert "impl Drop for BackendProcess" in shell
    assert "CloseRequested" in shell
    assert ".state::<BackendProcess>().stop()" in shell
    assert "terminate_backend_process" in shell
    assert 'Command::new("taskkill")' in shell
    assert '.arg("/T")' in shell
    assert "child.kill()" in shell
    assert "RACERZLAB_BACKEND_LOG" in shell


def test_tauri_config_uses_local_dev_and_dist_assets() -> None:
    config_path = PROJECT_ROOT / "ui/src-tauri/tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    text = config_path.read_text(encoding="utf-8")

    assert config["productName"] == "RacerZLab"
    assert config["identifier"] == "com.racelab.garage"
    assert config["build"]["devUrl"] == "http://127.0.0.1:5173"
    assert config["build"]["frontendDist"] == "../dist"
    assert config["build"]["beforeBuildCommand"] == "npm run build:desktop"
    assert config["app"]["windows"][0]["title"] == "RacerZLab"
    assert "bin/racerzlab-backend.exe" in config["bundle"]["resources"]

    assert "allowlist" not in text
    assert '"all": true' not in text
    assert "updater" not in text.lower()


def test_tauri_icon_paths_are_local_and_exist() -> None:
    config_path = PROJECT_ROOT / "ui/src-tauri/tauri.conf.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    icons_dir = PROJECT_ROOT / "ui/src-tauri/icons"
    icon_paths = config["bundle"]["icon"]

    assert (icons_dir / "icon.ico").exists()
    assert icon_paths

    for icon_path in icon_paths:
        assert not re.match(r"https?://", icon_path)
        assert not Path(icon_path).is_absolute()
        assert ".." not in Path(icon_path).parts
        assert (PROJECT_ROOT / "ui/src-tauri" / icon_path).exists()


def test_windows_icon_file_is_valid_ico_container() -> None:
    icon_path = PROJECT_ROOT / "ui/src-tauri/icons/icon.ico"
    data = icon_path.read_bytes()
    reserved, icon_type, image_count = struct.unpack_from("<HHH", data, 0)

    assert reserved == 0
    assert icon_type == 1
    assert image_count >= 1

    sizes: set[tuple[int, int]] = set()
    for index in range(image_count):
        entry_offset = 6 + index * 16
        width_byte, height_byte = struct.unpack_from("<BB", data, entry_offset)
        width = 256 if width_byte == 0 else width_byte
        height = 256 if height_byte == 0 else height_byte
        sizes.add((width, height))
        image_size, image_offset = struct.unpack_from("<II", data, entry_offset + 8)
        image = data[image_offset : image_offset + image_size]
        assert image.startswith(b"\x89PNG\r\n\x1a\n")

    assert {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}.issubset(sizes)


def test_windows_small_png_icon_variants_exist() -> None:
    icons_dir = PROJECT_ROOT / "ui/src-tauri/icons"

    for size in (16, 24, 32, 48, 64):
        icon_path = icons_dir / f"{size}x{size}.png"
        data = icon_path.read_bytes()
        width, height = struct.unpack_from(">II", data, 16)

        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        assert (width, height) == (size, size)


def test_tauri_config_has_no_runtime_remote_url() -> None:
    text = (PROJECT_ROOT / "ui/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
    urls = re.findall(r"https?://[^\"'\s]+", text)
    assert urls
    assert all(
        url.startswith(("http://127.0.0.1", "http://localhost", "https://schema.tauri.app"))
        for url in urls
    )


def test_frontend_runtime_has_no_remote_production_urls() -> None:
    text_suffixes = {".css", ".html", ".js", ".json", ".ts", ".tsx"}
    frontend_paths = [
        PROJECT_ROOT / "ui/index.html",
        *(path for path in Path(PROJECT_ROOT / "ui/src").rglob("*.*") if path.suffix in text_suffixes),
    ]

    for path in frontend_paths:
        text = path.read_text(encoding="utf-8")
        urls = re.findall(r"https?://[^\"'\s]+", text)
        assert all(url.startswith(("http://127.0.0.1", "http://localhost")) for url in urls)
        assert not re.search(r"<script[^>]+https?://|<link[^>]+https?://", text, flags=re.IGNORECASE)
