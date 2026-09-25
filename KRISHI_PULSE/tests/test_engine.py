"""Unit tests for the KRISHI_PULSE decision engine.
Run with: python -m pytest tests/ -v   (or python -m unittest tests.test_engine -v)
"""
import sys, os, unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from krishi_pulse.models import Farm, SoilReading, Weather, ForecastDay
from krishi_pulse.engine import advise, detect_pests, et0_hargreaves, stage_for
from krishi_pulse.knowledge import CROPS


def mk_farm(**kw):
    base = dict(id="t1", name="Test plot", crop="tomato", soil_type="red_loam",
                sowing_date="2026-08-01", area_acres=1.0, irrigation="drip")
    base.update(kw)
    return Farm.from_dict(base)


def mk_weather(tmax=32, tmin=21, rain=0.0, rprob=0.1, humidity=55, days=5):
    fdays = [ForecastDay((datetime.now()+timedelta(days=i)).date().isoformat(), tmax, tmin, rain, rprob, humidity, 8)
              for i in range(days)]
    return Weather(temp_c=(tmax+tmin)/2, humidity_pct=humidity, wind_kmh=8, rain_last_24h_mm=0, forecast=fdays)


class TestEngine(unittest.TestCase):
    def test_critical_dryness_triggers_irrigate(self):
        farm = mk_farm(sowing_date=(datetime.now()-timedelta(days=50)).date().isoformat())
        reading = SoilReading(ts=datetime.now().isoformat(), moisture_pct=15.0)  # near wilting point (14)
        a = advise(farm, reading, mk_weather())
        self.assertEqual(a.primary.action, "IRRIGATE")
        self.assertEqual(a.primary.code, "WATER_CRITICAL")

    def test_wet_soil_says_wait(self):
        farm = mk_farm(sowing_date=(datetime.now()-timedelta(days=50)).date().isoformat())
        reading = SoilReading(ts=datetime.now().isoformat(), moisture_pct=26.0)  # near field capacity (28)
        a = advise(farm, reading, mk_weather(rain=0, rprob=0))
        self.assertEqual(a.primary.action, "WAIT")

    def test_saturated_soil_flags_waterlogging_over_irrigate(self):
        farm = mk_farm(sowing_date=(datetime.now()-timedelta(days=50)).date().isoformat())
        reading = SoilReading(ts=datetime.now().isoformat(), moisture_pct=31.0)  # above field capacity
        a = advise(farm, reading, mk_weather())
        self.assertEqual(a.primary.code, "WATERLOGGING")
        self.assertEqual(a.primary.action, "ACT")

    def test_dependable_rain_avoids_irrigation(self):
        farm = mk_farm(sowing_date=(datetime.now()-timedelta(days=50)).date().isoformat())
        reading = SoilReading(ts=datetime.now().isoformat(), moisture_pct=19.0)  # below trigger (~22.4)
        a = advise(farm, reading, mk_weather(rain=30, rprob=0.9))
        self.assertIn(a.primary.code, ("WAIT_FOR_RAIN",))

    def test_bad_sensor_value_is_rejected(self):
        farm = mk_farm()
        reading = SoilReading(ts=datetime.now().isoformat(), moisture_pct=190.0)
        a = advise(farm, reading, mk_weather())
        self.assertEqual(a.primary.code, "SENSOR_INVALID")

    def test_stale_sensor_is_flagged(self):
        farm = mk_farm()
        reading = SoilReading(ts=(datetime.now()-timedelta(hours=30)).isoformat(), moisture_pct=20.0)
        a = advise(farm, reading, mk_weather())
        self.assertEqual(a.primary.code, "SENSOR_OFFLINE")

    def test_heat_stress_detected_at_flowering(self):
        farm = mk_farm(sowing_date=(datetime.now()-timedelta(days=75)).date().isoformat())  # flowering stage
        reading = SoilReading(ts=datetime.now().isoformat(), moisture_pct=25.0)
        a = advise(farm, reading, mk_weather(tmax=39, tmin=24))
        codes = [f.code for f in [a.primary]+a.others]
        self.assertIn("HEAT_STRESS", codes)

    def test_disease_risk_from_humid_mild_forecast(self):
        farm = mk_farm(sowing_date=(datetime.now()-timedelta(days=50)).date().isoformat())
        reading = SoilReading(ts=datetime.now().isoformat(), moisture_pct=25.0)
        a = advise(farm, reading, mk_weather(tmax=24, tmin=16, humidity=90, rain=5, rprob=0.6))
        codes = [f.code for f in [a.primary]+a.others]
        self.assertIn("DISEASE_RISK", codes)

    def test_low_ph_flagged(self):
        farm = mk_farm(sowing_date=(datetime.now()-timedelta(days=50)).date().isoformat())
        reading = SoilReading(ts=datetime.now().isoformat(), moisture_pct=25.0, ph=4.8)
        a = advise(farm, reading, mk_weather())
        codes = [f.code for f in [a.primary]+a.others]
        self.assertIn("PH_OFF", codes)

    def test_stage_progression(self):
        crop = CROPS["tomato"]
        self.assertEqual(stage_for(crop, 0).name, "Establishment")
        self.assertEqual(stage_for(crop, 26).name, "Vegetative")
        self.assertEqual(stage_for(crop, 1000).name, "Ripening")

    def test_et0_increases_with_temperature_range(self):
        self.assertGreater(et0_hargreaves(38, 20), et0_hargreaves(28, 20))

    def test_confidence_drops_with_bad_sensor(self):
        farm = mk_farm()
        good = advise(farm, SoilReading(ts=datetime.now().isoformat(), moisture_pct=20.0), mk_weather())
        bad = advise(farm, SoilReading(ts=datetime.now().isoformat(), moisture_pct=-5.0), mk_weather())
        self.assertGreater(good.confidence["score"], bad.confidence["score"])

    def test_pest_detection_ranks_matching_signs(self):
        result = detect_pests("maize", ["windowpanes_on_leaves", "frass_in_whorl", "caterpillar_seen"])
        self.assertEqual(result["matches"][0]["key"], "fall_armyworm")
        self.assertEqual(len(result["matches"][0]["matched_signs"]), 3)
        self.assertTrue(result["matches"][0]["harm"])

    def test_pest_detection_rejects_unknown_crop(self):
        with self.assertRaises(KeyError):
            detect_pests("banana", ["leaf_curl"])


if __name__ == "__main__":
    unittest.main()
