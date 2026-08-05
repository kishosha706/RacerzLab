from __future__ import annotations

import math

import pytest

from racelab_engine.analysis.damper_response import _dominant_psd


def _sine(*, frequency_hz: float = 5.0, rate_hz: float = 60.0, seconds: float = 4.0):
    times = [index / rate_hz for index in range(round(rate_hz * seconds))]
    values = [math.sin(2.0 * math.pi * frequency_hz * timestamp) for timestamp in times]
    return values, times


def test_psd_reports_a_repeated_peak_from_a_continuous_stable_clock() -> None:
    values, times = _sine()
    evidence = {}

    frequency, power = _dominant_psd(values, times, evidence=evidence)

    assert frequency == pytest.approx(5.0, abs=0.5)
    assert power is not None and power > 0.0
    assert evidence["qualified_window_count"] == 1
    assert evidence["repeated"] is True
    assert evidence["agreeing_peak_count"] == 2
    assert evidence["effective_sample_rates_hz"] == pytest.approx([60.0])
    assert evidence["continuous_window_durations_s"][0] > 3.9
    assert evidence["frequency_resolution_hz"]


def test_psd_does_not_bridge_short_disjoint_windows() -> None:
    values, times = _sine(seconds=0.54)
    times = times[:16] + [timestamp + 10.0 for timestamp in times[16:32]]

    assert _dominant_psd(values[:32], times) == (None, None)


def test_psd_withholds_irregular_clipped_and_non_repeated_signals() -> None:
    values, times = _sine()
    irregular = [timestamp + (0.002 if index % 2 else 0.0) for index, timestamp in enumerate(times)]
    assert _dominant_psd(values, irregular) == (None, None)

    clipped = [1.0 if value > 0.0 else -1.0 for value in values]
    assert _dominant_psd(clipped, times) == (None, None)

    split = len(values) // 2
    mixed = [
        math.sin(2.0 * math.pi * (3.0 if index < split else 11.0) * timestamp)
        for index, timestamp in enumerate(times)
    ]
    assert _dominant_psd(mixed, times) == (None, None)


def test_psd_withholds_short_duration() -> None:
    values, times = _sine(seconds=0.8)

    assert _dominant_psd(values, times) == (None, None)
