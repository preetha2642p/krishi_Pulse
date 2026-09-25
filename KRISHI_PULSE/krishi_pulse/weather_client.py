"""Weather source: live Open-Meteo (no key needed) with a deterministic offline fallback.

Open-Meteo is free and keyless, which matters for smallholder-facing tools where
asking a farmer (or a student project) to manage an API key is friction. If the
network call fails for any reason, we fall back to a seeded synthetic forecast so
the app still runs end to end offline / in a sandbox.
"""
from __future__ import annotations
import random
from datetime import datetime, timedelta
from typing import Optional

try:
    import requests
except ImportError:      # pragma: no cover
    requests = None

from .models import Weather, ForecastDay

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_weather(lat: float, lon: float, days: int = 5) -> Weather:
    if requests is not None and lat and lon:
        try:
            return _fetch_live(lat, lon, days)
        except Exception:
            pass
    return _synthetic(lat, lon, days)


def _fetch_live(lat: float, lon: float, days: int) -> Weather:
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                  "precipitation_probability_max,relative_humidity_2m_mean,wind_speed_10m_max",
        "forecast_days": days, "timezone": "auto",
    }
    r = requests.get(OPEN_METEO_URL, params=params, timeout=6)
    r.raise_for_status()
    j = r.json()
    cur, daily = j["current"], j["daily"]
    fdays = [ForecastDay(
        date=daily["time"][i], tmax_c=daily["temperature_2m_max"][i], tmin_c=daily["temperature_2m_min"][i],
        rain_mm=daily.get("precipitation_sum", [0]*days)[i],
        rain_prob=(daily.get("precipitation_probability_max", [0]*days)[i] or 0) / 100,
        humidity_pct=daily.get("relative_humidity_2m_mean", [65]*days)[i] or 65,
        wind_kmh=daily.get("wind_speed_10m_max", [8]*days)[i] or 8,
    ) for i in range(len(daily["time"]))]
    return Weather(temp_c=cur["temperature_2m"], humidity_pct=cur["relative_humidity_2m"],
                    wind_kmh=cur.get("wind_speed_10m", 8), rain_last_24h_mm=fdays[0].rain_mm if fdays else 0,
                    forecast=fdays)


def _synthetic(lat: float, lon: float, days: int) -> Weather:
    """Seeded so the same farm gets a stable, plausible-looking forecast in demos."""
    rng = random.Random(int((lat or 12.9) * 1000) + int((lon or 76.6) * 1000) + datetime.now().timetuple().tm_yday)
    base_max, base_min = 31 + rng.uniform(-3, 3), 20 + rng.uniform(-3, 3)
    fdays = []
    today = datetime.now().date()
    for i in range(days):
        d = today + timedelta(days=i)
        drift = rng.uniform(-2, 2)
        rain_p = max(0.0, min(1.0, rng.uniform(0, 0.6) + (0.2 if rng.random() < 0.3 else 0)))
        rain_mm = round(rng.uniform(0, 22), 1) if rain_p > 0.3 else 0.0
        fdays.append(ForecastDay(d.isoformat(), round(base_max + drift, 1), round(base_min + drift, 1),
                                  rain_mm, round(rain_p, 2), round(55 + rng.uniform(-10, 25), 0), round(6 + rng.uniform(0, 12), 0)))
    return Weather(temp_c=round((base_max + base_min) / 2, 1), humidity_pct=fdays[0].humidity_pct,
                    wind_kmh=fdays[0].wind_kmh, rain_last_24h_mm=0.0, forecast=fdays)
