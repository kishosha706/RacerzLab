from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_platform_consumes_server_qualified_damper_psd_and_explains_withholding() -> None:
    platform = (ROOT / "ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")
    component = (ROOT / "ui/src/components/DamperSpectrumSummary.tsx").read_text(encoding="utf-8")
    client = (ROOT / "ui/src/api/client.ts").read_text(encoding="utf-8")

    assert "<DamperSpectrumSummary" in platform
    assert "/damper-response" in client
    assert "PSD withheld" in component
    assert "payload.run_id !== runId || payload.selected_lap !== lap" in component
    assert "Damper spectrum response did not match the selected run and lap." in component
    assert "Gaps, clock jitter, clipping, short windows, and non-repeated peaks are withheld" in component
    assert "Not measured damper force" in component


def test_every_interactive_surface_binds_to_its_auditable_contract_id() -> None:
    consumers = {
        "matched_position_time_delta": "ui/src/components/TimeDeltaComparison.tsx",
        "platform_channel_overlay": "ui/src/tabs/PlatformTab.tsx",
        "track_position_map": "ui/src/tabs/TrackMapTab.tsx",
        "damper_velocity_histogram": "ui/src/components/ShockHistogram.tsx",
        "damper_psd": "ui/src/components/DamperSpectrumSummary.tsx",
        "engineering_metrics": "ui/src/components/EngineeringSystemsComparison.tsx",
        "reproducible_report": "racelab_engine/reports/markdown_report.py",
    }
    for surface_id, relative_path in consumers.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert surface_id in source, f"{surface_id} is not bound to {relative_path}"


def test_dial_in_exposes_downloadable_controlled_test_certificate() -> None:
    dial_in = (ROOT / "ui/src/tabs/DialInTab.tsx").read_text(encoding="utf-8")
    client = (ROOT / "ui/src/api/client.ts").read_text(encoding="utf-8")

    assert "Open full certificate" in dial_in
    assert "Download Markdown" in dial_in
    assert "The workflow response itself cannot publish a target or Keep/Undo verdict." in dial_in
    assert "make the server re-derive the exact current-session P19 outcome" in dial_in
    assert "/report`" in client
