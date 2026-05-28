"""Tests for optional signal smoothing helpers."""

from __future__ import annotations

import math

from racelab_engine.analysis.smoothing import (
    savitzky_golay_5point,
    simple_moving_average,
    smooth_edges,
)


class TestSavitzkyGolay5Point:
    def _assert_interior_all(self, values: list[float], expected: float) -> None:
        smoothed = savitzky_golay_5point(values)
        assert all(smoothed[i] == expected for i in range(2, len(values) - 2))

    def test_constant_signal_remains_constant(self) -> None:
        self._assert_interior_all([5.0] * 20, 5.0)

    def test_edges_are_none(self) -> None:
        smoothed = savitzky_golay_5point([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])
        assert smoothed[0] is None and smoothed[1] is None and smoothed[-1] is None and smoothed[-2] is None

    def test_short_array_returns_all_none(self) -> None:
        assert all(v is None for v in savitzky_golay_5point([1.0, 2.0, 3.0]))

    def test_empty_array(self) -> None:
        assert savitzky_golay_5point([]) == []

    def test_spike_reduced(self) -> None:
        spike_val = savitzky_golay_5point([0.0] * 5 + [10.0] + [0.0] * 5)[5]
        assert spike_val is not None and spike_val < 10.0 and spike_val > 0.0

    def test_no_phase_shift_on_symmetric_signal(self) -> None:
        n, center = 21, 10
        values = [float(i) if i <= center else float(n - 1 - i) for i in range(n)]
        smoothed = savitzky_golay_5point(values)
        left3, right3 = smoothed[center - 3], smoothed[center + 3]
        left4, right4 = smoothed[center - 4], smoothed[center + 4]
        if left3 is not None and right3 is not None:
            assert abs(left3 - right3) < 1e-10
        if left4 is not None and right4 is not None:
            assert abs(left4 - right4) < 1e-10

    def test_linear_signal_preserved(self) -> None:
        values = [float(i) for i in range(20)]
        smoothed = savitzky_golay_5point(values)
        for i in range(2, len(values) - 2):
            v = smoothed[i]
            assert v is not None
            assert abs(v - values[i]) < 1e-10


class TestSimpleMovingAverage:
    def test_constant_signal(self) -> None:
        self._assert_interior_all([3.0] * 15, 3.0)

    def _assert_interior_all(self, values: list[float], expected: float) -> None:
        smoothed = simple_moving_average(values, window=5)
        assert all(smoothed[i] == expected for i in range(2, len(values) - 2))

    def test_edges_are_none(self) -> None:
        smoothed = simple_moving_average([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], window=5)
        assert smoothed[0] is None and smoothed[1] is None and smoothed[-1] is None and smoothed[-2] is None

    def test_short_array(self) -> None:
        assert all(v is None for v in simple_moving_average([1.0, 2.0], window=5))

    def test_empty_array(self) -> None:
        assert simple_moving_average([]) == []

    def test_noise_reduced(self) -> None:
        smoothed = simple_moving_average([0.0] * 10 + [5.0] * 5 + [0.0] * 10, window=5)
        interior = [v for v in smoothed if v is not None]
        assert all(0.0 <= v <= 5.0 for v in interior)


class TestSmoothEdges:
    def test_shorter_output(self) -> None:
        assert len(smooth_edges([float(i) for i in range(20)], window=5)) == 16

    def test_too_short_returns_empty(self) -> None:
        assert smooth_edges([1.0, 2.0], window=5) == []

    def test_empty_returns_empty(self) -> None:
        assert smooth_edges([]) == []
