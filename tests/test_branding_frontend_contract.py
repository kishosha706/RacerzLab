from __future__ import annotations

import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_startup_screen_uses_local_racerzlab_banner_and_keeps_session_actions() -> None:
    startup = _read("ui/src/components/StartupScreen.tsx")
    styles = _read("ui/src/styles.css")
    banner_path = PROJECT_ROOT / "ui/src/assets/racerzlab-banner.png"

    assert banner_path.exists()
    assert 'import racerzlabBanner from "../assets/racerzlab-banner.png";' in startup
    assert "launchSplashVisible" in startup
    assert "setLaunchSplashVisible(false)" in startup
    assert 'className="launch-splash-gate"' in startup
    assert "onClick={enterSessionPicker}" in startup
    assert 'data-launch-splash={launchSplashVisible}' in startup
    assert 'event.key === "Enter" || event.key === " "' in startup
    assert "launchSplashVisible ? (" in startup
    assert 'className="startup-bg-image"' in startup
    assert "src={racerzlabBanner}" in startup
    assert "onError={() => setBannerVisible(false)}" in startup
    assert 'className="start-brand-stage"' not in startup
    assert 'className="start-banner"' not in startup
    assert ".startup-bg-image" in styles
    assert ".launch-splash-gate" in styles
    assert 'data-launch-splash="true"] .startup-bg-image' in styles
    assert "opacity: 0.98;" in styles
    assert "brightness(1.08)" in styles
    assert "rgba(6, 8, 9, 0) 0%" in styles
    assert "rgba(6, 10, 16, 0.72)" in styles
    assert "position: absolute;" in styles
    assert "object-fit: cover;" in styles
    assert "New Session" in startup
    assert "Previous Sessions" in startup

    image_urls = re.findall(r"<img[^>]+src=[{'\"]([^}'\"]+)", startup)
    assert all(not url.startswith(("http://", "https://")) for url in image_urls)


def test_index_html_uses_racerzlab_title_and_local_favicon() -> None:
    index = _read("ui/index.html")

    assert "<title>RacerZLab</title>" in index
    assert '<link rel="icon" type="image/png" href="/favicon.png" />' in index
    assert (PROJECT_ROOT / "ui/public/favicon.png").exists()
    assert "http://www." not in index
    assert not re.search(r"<(?:link|script|img)[^>]+https?://", index, flags=re.IGNORECASE)


def test_tauri_config_references_generated_racerzlab_icons() -> None:
    config = json.loads(_read("ui/src-tauri/tauri.conf.json"))
    icon_paths = config["bundle"]["icon"]

    assert config["productName"] == "RacerZLab"
    assert config["app"]["windows"][0]["title"] == "RacerZLab"
    assert {
        "icons/32x32.png",
        "icons/128x128.png",
        "icons/128x128@2x.png",
        "icons/icon.icns",
        "icons/icon.ico",
        "icons/icon.png",
    }.issubset(set(icon_paths))

    for icon_path in icon_paths:
        assert not re.match(r"https?://", icon_path)
        assert (PROJECT_ROOT / "ui/src-tauri" / icon_path).exists()
