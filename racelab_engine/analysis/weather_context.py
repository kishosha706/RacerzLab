"""
Weather-normalized context helpers.

Provides estimated air density and weather context labels.
Does NOT correct speed or aero values — only provides context for interpretation.

Standard reference: rho_standard = 1.225 kg/m³ at 15°C, 1013.25 hPa
"""

from __future__ import annotations

from dataclasses import dataclass, field
@dataclass
class WeatherContext:
    air_density_kg_m3: float | None = None
    air_density_ratio_to_standard: float | None = None
    weather_context_label: str = "Weather context unavailable"
    is_available: bool = False
    warnings: list[str] = field(default_factory=list)


# Standard sea-level conditions
RHO_STANDARD = 1.225  # kg/m³ at 15°C, 1013.25 hPa
GAS_CONSTANT_AIR = 287.058  # J/(kg·K)


def compute_air_density(air_temp_c: float | None, air_pressure_hpa: float | None) -> float | None:
    """
    Compute air density from temperature and pressure.

    Uses the ideal gas law: rho = P / (R_specific * T)

    Args:
        air_temp_c: Air temperature in Celsius.
        air_pressure_hpa: Air pressure in hectopascals (hPa).

    Returns:
        Air density in kg/m³, or None if inputs are missing.
    """
    if air_temp_c is None or air_pressure_hpa is None:
        return None
    temp_k = air_temp_c + 273.15
    if temp_k <= 0:
        return None
    pressure_pa = air_pressure_hpa * 100.0  # hPa -> Pa
    return pressure_pa / (GAS_CONSTANT_AIR * temp_k)


def compute_weather_context(
    air_temp_c: float | None,
    air_pressure_hpa: float | None,
) -> WeatherContext:
    """
    Compute weather context from available session data.

    Args:
        air_temp_c: Air temperature in Celsius.
        air_pressure_hpa: Air pressure in hectopascals.

    Returns:
        WeatherContext with density, ratio, and label.
    """
    density = compute_air_density(air_temp_c, air_pressure_hpa)
    if density is None:
        return WeatherContext(
            is_available=False,
            warnings=["Air temperature or pressure not available."],
        )

    ratio = density / RHO_STANDARD

    if ratio > 1.05:
        label = "High density air — more aero load and drag than standard"
    elif ratio > 1.02:
        label = "Slightly dense air — aero load may be slightly elevated"
    elif ratio > 0.98:
        label = "Near-standard air density"
    elif ratio > 0.95:
        label = "Slightly thin air — aero load may be slightly reduced"
    else:
        label = "Thin air — less aero load and drag than standard"

    warnings: list[str] = []
    if ratio < 0.95 or ratio > 1.05:
        warnings.append(
            f"Air density is {ratio:.1%} of standard ({density:.3f} kg/m³). "
            "This is a weather-normalized context note, not a speed correction."
        )

    return WeatherContext(
        air_density_kg_m3=density,
        air_density_ratio_to_standard=ratio,
        weather_context_label=label,
        is_available=True,
        warnings=warnings,
    )


def density_differs_significantly(
    ctx_a: WeatherContext,
    ctx_b: WeatherContext,
    threshold: float = 0.03,
) -> bool:
    """Check if two weather contexts differ significantly."""
    if not ctx_a.is_available or not ctx_b.is_available:
        return False
    if ctx_a.air_density_ratio_to_standard is None or ctx_b.air_density_ratio_to_standard is None:
        return False
    return abs(ctx_a.air_density_ratio_to_standard - ctx_b.air_density_ratio_to_standard) > threshold
