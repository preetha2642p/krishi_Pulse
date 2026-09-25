"""Plain data containers. Everything is JSON-friendly so it can travel over the API."""
from __future__ import annotations
from dataclasses import dataclass, field, fields
from typing import Optional


def _pick(cls, d: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class Farm:
    id: str
    name: str
    crop: str                    # key in knowledge.CROPS
    soil_type: str               # key in knowledge.SOILS
    sowing_date: str             # YYYY-MM-DD
    area_acres: float = 1.0
    irrigation: str = "drip"     # drip | sprinkler | furrow | flood
    lat: float = 0.0
    lon: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "Farm":
        return _pick(cls, d)


@dataclass
class SoilReading:
    ts: str                      # ISO timestamp of the sensor reading
    moisture_pct: float          # volumetric water content, %
    temp_c: Optional[float] = None
    ph: Optional[float] = None
    ec_ds_m: Optional[float] = None
    n_mg_kg: Optional[float] = None
    battery_pct: Optional[float] = None
    moisture_24h_ago_pct: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "SoilReading":
        return _pick(cls, d)


@dataclass
class ForecastDay:
    date: str
    tmax_c: float
    tmin_c: float
    rain_mm: float = 0.0
    rain_prob: float = 0.0       # 0..1
    humidity_pct: float = 65.0
    wind_kmh: float = 8.0

    @classmethod
    def from_dict(cls, d: dict) -> "ForecastDay":
        return _pick(cls, d)


@dataclass
class Weather:
    temp_c: float
    humidity_pct: float
    wind_kmh: float = 8.0
    rain_last_24h_mm: float = 0.0
    forecast: list = field(default_factory=list)   # forecast[0] is today

    @classmethod
    def from_dict(cls, d: dict) -> "Weather":
        w = _pick(cls, d)
        w.forecast = [x if isinstance(x, ForecastDay) else ForecastDay.from_dict(x)
                      for x in d.get("forecast", [])]
        return w
