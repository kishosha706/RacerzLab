from __future__ import annotations

from pathlib import Path


def test_workbench_trace_channels_include_platform_shock_channels() -> None:
    source = Path("ui/src/constants/workbenchChannels.ts").read_text(encoding="utf-8")
    required_channels = [
        "lf_shock_defl_in",
        "rf_shock_defl_in",
        "lr_shock_defl_in",
        "rr_shock_defl_in",
        "lf_shock_vel_in_s",
        "rf_shock_vel_in_s",
        "lr_shock_vel_in_s",
        "rr_shock_vel_in_s",
        "lf_shock_static_defl_in",
        "rf_shock_static_defl_in",
        "lr_shock_static_defl_in",
        "rr_shock_static_defl_in",
        "lf_shock_defl_delta_in",
        "rf_shock_defl_delta_in",
        "lr_shock_defl_delta_in",
        "rr_shock_defl_delta_in",
    ]

    for channel in required_channels:
        assert f'"{channel}"' in source, f"Workbench trace channels are missing {channel}"


def test_platform_shocks_mounts_shock_reader_only_in_shocks_panel() -> None:
    source = Path("ui/src/tabs/PlatformTab.tsx").read_text(encoding="utf-8")
    assert "fetchShockReader" in source
    assert "<ShockReaderPanel" in source
    assert 'case "shocks": return renderShocksPanel();' in source
    assert "DialIn" not in Path("ui/src/components/ShockReaderPanel.tsx").read_text(encoding="utf-8")
