#!/usr/bin/env python3
"""Seed a couple of demo farms with a few days of readings, so the dashboard
has something to show right after setup. Safe to re-run.

Usage: python seed_demo.py
"""
import sys, os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from krishi_pulse import store
from krishi_pulse.models import Farm, SoilReading

DEMO_FARMS = [
    dict(id="demo-tomato", name="Chikkamagalur tomato plot", crop="tomato", soil_type="red_loam",
         sowing_date=(datetime.now() - timedelta(days=48)).date().isoformat(),
         area_acres=1.5, irrigation="drip", lat=13.31, lon=75.77),
    dict(id="demo-ragi", name="Banavara ragi field", crop="ragi", soil_type="black_clay",
         sowing_date=(datetime.now() - timedelta(days=30)).date().isoformat(),
         area_acres=2.0, irrigation="furrow", lat=13.28, lon=76.05),
]

READINGS = {
    "demo-tomato": [(4, 24.0), (3, 22.5), (2, 20.5), (1, 18.0), (0, 16.5)],
    "demo-ragi":   [(3, 30.0), (2, 27.5), (1, 25.0), (0, 23.0)],
}


def main():
    for f in DEMO_FARMS:
        store.upsert_farm(Farm.from_dict(f).__dict__)
    for farm_id, points in READINGS.items():
        for days_ago, moisture in points:
            ts = (datetime.now() - timedelta(days=days_ago)).isoformat(timespec="minutes")
            r = SoilReading(ts=ts, moisture_pct=moisture, temp_c=26.5, ph=6.3, ec_ds_m=1.0, n_mg_kg=32, battery_pct=76)
            store.add_reading(farm_id, r.__dict__)
    print(f"Seeded {len(DEMO_FARMS)} demo farms with sample readings into ./data/")


if __name__ == "__main__":
    main()
