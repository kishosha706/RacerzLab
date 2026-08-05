"""Tests for weather-normalized context helpers."""

from __future__ import annotations

from racelab_engine.analysis.weather_context import (
    WeatherContext,
    compute_air_density,
    compute_weather_context,
    density_differs_significantly,
)


class TestComputeAirDensity:
    def test_standard_day(self):
        """Standard day (15°C, 1013.25 hPa) should give ~1.225 kg/m³."""
        density = compute_air_density(15.0, 1013.25)
        assert density is not None
        assert abs(density - 1.225) < 0.01

    def test_hot_day_lower_density(self):
        """Hot day (35°C) should give lower density."""
        density = compute_air_density(35.0, 1013.25)
        assert density is not None
        assert density < 1.2

    def test_cold_day_higher_density(self):
        """Cold day (0°C) should give higher density."""
        density = compute_air_density(0.0, 1013.25)
        assert density is not None
        assert density > 1.25

    def test_missing_temp_returns_none(self):
        """Missing temperature should return None."""
        assert compute_air_density(None, 1013.25) is None

    def test_missing_pressure_returns_none(self):
        """Missing pressure should return None."""
        assert compute_air_density(15.0, None) is None


class TestComputeWeatherContext:
    def test_standard_day_ratio_near_one(self):
        """Standard day should have ratio near 1.0."""
        ctx = compute_weather_context(15.0, 1013.25)
        assert ctx.is_available
        assert ctx.air_density_ratio_to_standard is not None
        assert abs(ctx.air_density_ratio_to_standard - 1.0) < 0.01

    def test_hot_day_ratio_lower(self):
        """Hot day should have ratio < 1.0."""
        ctx = compute_weather_context(35.0, 1013.25)
        assert ctx.is_available
        assert ctx.air_density_ratio_to_standard is not None
        assert ctx.air_density_ratio_to_standard < 0.98

    def test_missing_weather_returns_unavailable(self):
        """Missing weather data should return unavailable."""
        ctx = compute_weather_context(None, None)
        assert not ctx.is_available

    def test_extreme_density_has_warning(self):
        """Extreme density should produce a warning."""
        ctx = compute_weather_context(40.0, 1013.25)
        assert ctx.is_available
        assert len(ctx.warnings) > 0


class TestDensityDiffersSignificantly:
    def test_similar_density_no_diff(self):
        """Similar densities should not flag as different."""
        a = compute_weather_context(15.0, 1013.25)
        b = compute_weather_context(17.0, 1013.25)
        assert not density_differs_significantly(a, b)

    def test_different_density_flags(self):
        """Different densities should flag."""
        a = compute_weather_context(15.0, 1013.25)
        b = compute_weather_context(35.0, 1013.25)
        assert density_differs_significantly(a, b)

    def test_unavailable_returns_false(self):
        """Unavailable context should not flag."""
        a = compute_weather_context(15.0, 1013.25)
        b = WeatherContext()
        assert not density_differs_significantly(a, b)
