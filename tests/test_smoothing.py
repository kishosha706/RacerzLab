"""Tests for optional signal smoothing helpers."""

from __future__ import annotations

import math

from racelab_engine.analysis.smoothing import (
    savitzky_golay_5point,
    simple_moving_average,
    smooth_edges,
)


class TestSavitzkyGolay5Point:
    def test_constant_signal_remains_constant(self):
        values = [5.0] * 20
        smoothed = savitzky_golay_5point(values)
        # Interior values should remain 5.0
        for i in range(2, len(values) - 2):
            assert smoothed[i] == 5.0, f"Index {i}: expected 5.0, got {smoothed[i]}"

    def test_edges_are_none(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
        smoothed = savitzky_golay_5point(values)
        assert smoothed[0] is None
        assert smoothed[1] is None
        assert smoothed[-1] is None
        assert smoothed[-2] is None

    def test_short_array_returns_all_none(self):
        values = [1.0, 2.0, 3.0]
        smoothed = savitzky_golay_5point(values)
        assert all(v is None for v in smoothed)

    def test_empty_array(self):
        assert savitzky_golay_5point([]) == []

    def test_spike_reduced(self):
        # A single spike should be attenuated by smoothing
        values = [0.0] * 5 + [10.0] + [0.0] * 5
        smoothed = savitzky_golay_5point(values)
        # The spike at index 5 should be reduced
        spike_val = smoothed[5]
        assert spike_val is not None
        assert spike_val < 10.0, f"Spike not reduced: {spike_val}"
        assert spike_val > 0.0, f"Spike over-smoothed: {spike_val}"

    def test_no_phase_shift_on_symmetric_signal(self):
        # A symmetric triangle should remain symmetric after smoothing
        n = 21
        center = n // 2
        values = [float(i) if i <= center else float(n - 1 - i) for i in range(n)]
        smoothed = savitzky_golay_5point(values)
        # Check symmetry around center
        for offset in range(1, min(5, center)):
            left = smoothed[center - offset]
            right = smoothed[center + offset]
            if left is not None and right is not None:
                assert abs(left - right) < 1e-10, (
                    f"Asymmetry at offset {offset}: left={left}, right={right}"
                )

    def test_linear_signal_preserved(self):
        # A linear ramp should be preserved (quadratic can represent linear exactly)
        values = [float(i) for i in range(20)]
        smoothed = savitzky_golay_5point(values)
        for i in range(2, len(values) - 2):
            assert smoothed[i] is not None
            assert abs(smoothed[i] - values[i]) < 1e-10, (
                f"Index {i}: expected {values[i]}, got {smoothed[i]}"
            )


class TestSimpleMovingAverage:
    def test_constant_signal(self):
        values = [3.0] * 15
        smoothed = simple_moving_average(values, window=5)
        for i in range(2, len(values) - 2):
            assert smoothed[i] == 3.0

    def test_edges_are_none(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        smoothed = simple_moving_average(values, window=5)
        assert smoothed[0] is None
        assert smoothed[1] is None
        assert smoothed[-1] is None
        assert smoothed[-2] is None

    def test_short_array(self):
        values = [1.0, 2.0]
        smoothed = simple_moving_average(values, window=5)
        assert all(v is None for v in smoothed)

    def test_empty_array(self):
        assert simple_moving_average([]) == []

    def test_noise_reduced(self):
        values = [0.0] * 10 + [5.0, 5.0, 5.0, 5.0, 5.0] + [0.0] * 10
        smoothed = simple_moving_average(values, window=5)
        # The transition region should be smoothed
        interior = [v for v in smoothed if v is not None]
        assert all(0.0 <= v <= 5.0 for v in interior)


class TestSmoothEdges:
    def test_shorter_output(self):
        values = [float(i) for i in range(20)]
        trimmed = smooth_edges(values, window=5)
        assert len(trimmed) == len(values) - 4  # window - 1 = 4 removed

    def test_too_short_returns_empty(self):
        assert smooth_edges([1.0, 2.0], window=5) == []

    def test_empty_returns_empty(self):
        assert smooth_edges([]) == []
