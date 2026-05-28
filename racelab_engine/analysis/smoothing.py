"""
Optional signal smoothing helpers for noisy derivative-based channels.

Design principles:
- Raw channels remain unchanged.
- Smoothed channels are clearly named with "_smoothed" suffix.
- No phase shift (zero-phase via forward-backward application).
- Edge values are truncated (smoothed output is shorter or NaN-padded).
- No SciPy dependency — pure Python implementation.
- Smoothing is opt-in: callers must explicitly request smoothed channels.

Available functions:
  savitzky_golay_5point(values) — 5-point quadratic Savitzky-Golay
  simple_moving_average(values, window) — centered SMA (zero-phase)
  smooth_edges(values, window) — edge-trimmed smoothing

Future considerations:
- SciPy's savgol_filter would be faster for large arrays.
- EKF sensor fusion is a separate research topic.
"""

from __future__ import annotations

from typing import Any


def savitzky_golay_5point(values: list[float]) -> list[float | None]:
    """
    5-point quadratic Savitzky-Golay smoothing.

    Coefficients for 5-point, quadratic polynomial:
      y_smooth[i] = (-3*y[i-2] + 12*y[i-1] + 17*y[i] + 12*y[i+1] - 3*y[i+2]) / 35

    Returns None-padded list of same length. First 2 and last 2 values are None
    (insufficient neighbors for the 5-point window).

    This is a zero-phase (centered) filter — no phase shift.
    """
    n = len(values)
    if n < 5:
        return [None] * n

    result: list[float | None] = [None] * n
    for i in range(2, n - 2):
        y_vals = [values[i + j] for j in range(-2, 3)]
        if any(v is None for v in y_vals):
            continue
        smoothed = (
            -3 * y_vals[0]
            + 12 * y_vals[1]
            + 17 * y_vals[2]
            + 12 * y_vals[3]
            - 3 * y_vals[4]
        ) / 35.0
        result[i] = smoothed
    return result


def simple_moving_average(values: list[float], window: int = 5) -> list[float | None]:
    """
    Centered simple moving average (zero-phase).

    For odd window sizes, the output is centered so there is no phase shift.
    Edge values (first and last window//2) are None.

    Args:
        values: Input signal.
        window: Window size (must be odd, minimum 3).

    Returns:
        Smoothed signal with None-padded edges, same length as input.
    """
    if window < 3:
        window = 3
    if window % 2 == 0:
        window += 1  # Force odd for centered window

    n = len(values)
    half = window // 2
    result: list[float | None] = [None] * n

    for i in range(half, n - half):
        segment = values[i - half : i + half + 1]
        clean = [v for v in segment if v is not None]
        if len(clean) < window:
            continue
        result[i] = sum(clean) / len(clean)

    return result


def smooth_edges(values: list[float], window: int = 5) -> list[float]:
    """
    Edge-trimmed smoothing: returns only the interior values that can be smoothed.

    Unlike savitzky_golay_5point and simple_moving_average which return
    None-padded arrays of the same length, this returns a shorter array
    containing only valid smoothed values.

    Args:
        values: Input signal.
        window: Window size (must be odd).

    Returns:
        List of smoothed values (shorter than input by window-1).
    """
    if window < 3:
        window = 3
    if window % 2 == 0:
        window += 1

    half = window // 2
    if len(values) < window:
        return []

    smoothed = simple_moving_average(values, window)
    return [v for v in smoothed[half : len(smoothed) - half] if v is not None]


def _numeric(value: Any) -> float | None:
    """Safely convert to float, returning None for missing/bad values."""
    if value is None:
        return None
    try:
        v = float(value)
        return None if (v != v or v == float("inf") or v == float("-inf")) else v
    except (TypeError, ValueError):
        return None
