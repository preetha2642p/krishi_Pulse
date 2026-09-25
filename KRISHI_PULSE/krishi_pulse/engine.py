"""The decision engine.

It reads soil, weather, crop and sensor health *together* and returns one primary
action (IRRIGATE / WAIT / ACT) plus any secondary alerts. Every finding carries the
reasoning steps behind it so the farmer (or an extension officer) can check the logic.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional

from .knowledge import CROPS, SOILS, Crop, Stage, pest_harm, pests_for
from .models import Farm, SoilReading, Weather, ForecastDay

IRRIGATION_EFFICIENCY = {"drip": 0.90, "sprinkler": 0.75, "furrow": 0.60, "flood": 0.55}
M2_PER_ACRE = 4046.86
RA_MM_DAY = 15.0            # extraterrestrial radiation, mm/day equivalent (tropical average)
STALE_HOURS = 6
DEAD_HOURS = 24

IRRIGATE, WAIT, ACT = "IRRIGATE", "WAIT", "ACT"
_RANK = {ACT: 2, IRRIGATE: 1, WAIT: 0}

LABELS = {
    IRRIGATE: {"en": "Irrigate", "kn": "ನೀರು ಹಾಯಿಸಿ", "hi": "सिंचाई करें", "te": "నీరు పెట్టండి", "ta": "நீர்ப்பாசனம் செய்யவும்", "ml": "നനയ്ക്കുക"},
    WAIT:     {"en": "Wait", "kn": "ಕಾಯಿರಿ", "hi": "रुकें", "te": "వేచి ఉండండి", "ta": "காத்திருக்கவும்", "ml": "കാത്തിരിക്കുക"},
    ACT:      {"en": "Act on a risk", "kn": "ಅಪಾಯದ ಬಗ್ಗೆ ಕ್ರಮ ಕೈಗೊಳ್ಳಿ", "hi": "जोखिम पर कार्रवाई करें", "te": "ప్రమాదంపై చర్య", "ta": "ஆபத்தில் நடவடிக்கை", "ml": "അപകടത്തിൽ പ്രവർത്തിക്കുക"},
}


# ------------------------------------------------------------------ result types
@dataclass
class Step:
    label: str      # data source: Soil / Weather / Crop / Sensor / Action
    fact: str       # what the data says
    meaning: str    # what that implies


@dataclass
class Finding:
    code: str
    action: str
    severity: int           # 0 info, 1 plan, 2 act soon, 3 urgent
    title: str
    detail: str
    when: str = ""
    steps: list = field(default_factory=list)


@dataclass
class Advice:
    farm: dict
    generated_at: str
    stage: str
    primary: Finding
    others: list
    confidence: dict
    metrics: dict
    labels: dict
    sms: str


# ------------------------------------------------------------------ helpers
def et0_hargreaves(tmax: float, tmin: float) -> float:
    """Reference evapotranspiration (mm/day) from temperature only (Hargreaves)."""
    tmean = (tmax + tmin) / 2
    return max(0.0, 0.0023 * (tmean + 17.8) * math.sqrt(max(tmax - tmin, 0.1)) * RA_MM_DAY)


def stage_for(crop: Crop, das: int) -> Stage:
    """Growth stage from days after sowing."""
    if das <= 0:
        return crop.stages[0]
    total = 0
    for st in crop.stages:
        total += st.days
        if das <= total:
            return st
    return crop.stages[-1]


def detect_pests(crop_key: str, symptoms: list[str], notes: str = "") -> dict:
    """Rank likely pests from observed field signs; this is not an image model."""
    if crop_key not in CROPS:
        raise KeyError(crop_key)
    selected = {str(symptom).strip().lower() for symptom in symptoms if str(symptom).strip()}
    ranked = []
    for pest in pests_for(crop_key):
        matched = [symptom for symptom in pest.symptoms if symptom in selected]
        if not matched:
            continue
        coverage = len(matched) / len(pest.symptoms)
        confidence = min(0.96, 0.42 + coverage * 0.62)
        ranked.append({
            "key": pest.key,
            "name": pest.name,
            "confidence": round(confidence, 2),
            "matched_signs": matched,
            "harm": pest_harm(pest.key),
            "action": pest.action,
            "urgency": pest.urgency,
        })
    ranked.sort(key=lambda result: (result["confidence"], len(result["matched_signs"])), reverse=True)
    return {
        "crop": CROPS[crop_key].name,
        "observed_signs": sorted(selected),
        "field_notes": notes.strip(),
        "matches": ranked[:3],
        "disclaimer": "Scout confirmation is needed before treatment. Do not spray from this result alone.",
    }


def effective_rain_mm(days: list, horizon: int = 2) -> float:
    """Rain we can rely on: light showers evaporate, and every forecast is uncertain."""
    return sum(d.rain_mm * d.rain_prob * 0.8 for d in days[:horizon] if d.rain_mm >= 3)


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)


def _litres(mm: float, acres: float) -> int:
    return int(round(mm * acres * M2_PER_ACRE, -1))   # 1 mm over 1 m2 = 1 litre


# ------------------------------------------------------------------ main entry
def advise(farm: Farm, soil_reading: SoilReading, weather: Weather,
           now: Optional[datetime] = None) -> Advice:
    now = now or datetime.now()
    crop, soil = CROPS[farm.crop], SOILS[farm.soil_type]
    das = (now.date() - date.fromisoformat(farm.sowing_date)).days
    stage = stage_for(crop, das)
    fc, pwp = soil.field_capacity, soil.wilting_point
    aw = fc - pwp                                        # available water, % points
    root_mm = stage.root_cm * 10
    trigger = fc - stage.mad * aw                        # irrigate at/below this moisture
    m = soil_reading.moisture_pct
    fdays = weather.forecast or []
    today = fdays[0] if fdays else ForecastDay(now.date().isoformat(), weather.temp_c + 4, weather.temp_c - 4)

    et0 = et0_hargreaves(today.tmax_c, today.tmin_c)
    etc = et0 * stage.kc
    drop_pts_per_day = etc / root_mm * 100 if root_mm else 1.0
    days_to_trigger = max(0.0, (m - trigger) / drop_pts_per_day) if drop_pts_per_day > 0 else 99.0
    eff_rain = effective_rain_mm(fdays)
    depletion = max(0.0, min(1.0, (fc - m) / aw))

    findings: list = []
    notes: list = []          # data-quality notes shown with the confidence score
    penalty = 0.0

    # ---------------------------------------------------------- 1. sensor health
    age_h = (now - _parse_ts(soil_reading.ts)).total_seconds() / 3600
    sensor_ok = True
    if not (0 < m <= 60):
        sensor_ok = False
        findings.append(Finding("SENSOR_INVALID", ACT, 2, "Soil sensor reading looks wrong",
            f"A moisture reading of {m:.1f}% is not physically believable, so I am not using it for irrigation.",
            "Today",
            [Step("Sensor", f"Moisture reads {m:.1f}%", "Real soil sits between about 3% and 55%, so the probe or wiring is faulty."),
             Step("Action", "Irrigation advice paused", "Dig 10 cm and feel the soil by hand, then check the probe is fully in the soil and its cable is intact.")]))
        penalty += 0.45
        notes.append("Moisture sensor value is out of range.")
    elif age_h > DEAD_HOURS:
        sensor_ok = False
        findings.append(Finding("SENSOR_OFFLINE", ACT, 2, "Soil sensor has gone quiet",
            f"The last reading is {age_h:.0f} hours old, so I am not using it for irrigation.",
            "Today",
            [Step("Sensor", f"Last reading {age_h:.0f} h ago", "Data older than a day cannot tell me today's soil water."),
             Step("Action", "Check battery, network and probe position", "Meanwhile, dig 10 cm and test the soil by hand.")]))
        penalty += 0.35
        notes.append(f"Sensor data is {age_h:.0f} hours old.")
    elif age_h > STALE_HOURS:
        penalty += 0.10
        notes.append(f"Sensor reading is {age_h:.0f} hours old.")
    if soil_reading.battery_pct is not None and soil_reading.battery_pct < 15:
        penalty += 0.05
        notes.append(f"Sensor battery is low ({soil_reading.battery_pct:.0f}%).")
    if (soil_reading.moisture_24h_ago_pct is not None and sensor_ok
            and m - soil_reading.moisture_24h_ago_pct > 8 and weather.rain_last_24h_mm < 5):
        penalty += 0.15
        notes.append("Soil jumped more than 8 points with no matching rain: either you irrigated, or the sensor moved.")

    # ---------------------------------------------------------- 2. water decision
    if sensor_ok:
        need_mm = max(0.0, (fc - m) / 100 * root_mm)     # to bring the root zone back to field capacity
        eff = IRRIGATION_EFFICIENCY.get(farm.irrigation, 0.7)
        base = [
            Step("Soil", f"Moisture {m:.1f}% (wilting point {pwp:.0f}%, field capacity {fc:.0f}%)",
                 f"Root zone is {depletion*100:.0f}% depleted of plant-available water."),
            Step("Crop", f"{crop.name}, {stage.name} stage, day {max(das,0)} after sowing",
                 f"This stage should be irrigated when moisture falls to about {trigger:.1f}% (it tolerates {stage.mad*100:.0f}% depletion)."),
            Step("Weather", f"Today {today.tmin_c:.0f}-{today.tmax_c:.0f} °C gives ET0 of about {et0:.1f} mm",
                 f"The crop uses about {etc:.1f} mm/day, which lowers soil moisture roughly {drop_pts_per_day:.1f} points per day."),
        ]
        heavy = sum(d.rain_mm * d.rain_prob for d in fdays[:2])
        if m >= fc + 2 or (m >= fc - 1 and heavy >= 25):
            findings.append(Finding("WATERLOGGING", ACT, 2, "Soil is saturated - hold water and drain",
                f"Soil is at {m:.1f}% against a field capacity of {fc:.0f}%"
                + (f", and about {heavy:.0f} mm of rain is likely soon." if heavy >= 10 else "."),
                "Before the next rain",
                base[:1] + [Step("Weather", f"Expected rain next 48 h: {heavy:.0f} mm",
                    "Roots need air. Standing water for more than a day or two invites root rot, and fertiliser will wash out."),
                    Step("Action", "Do not irrigate. Open field drains and bunds.", "Delay any fertiliser top-dressing until the field drains.")]))
        elif m <= pwp + 2:
            gross = need_mm / eff
            findings.append(Finding("WATER_CRITICAL", IRRIGATE, 3, "Irrigate now - crop is near wilting",
                f"Soil moisture {m:.1f}% is almost at the wilting point ({pwp:.0f}%). Give about {gross:.0f} mm ({_litres(gross, farm.area_acres):,} litres for {farm.area_acres:g} acre).",
                "Right now, then check again in 2-3 days",
                base + [Step("Action", f"Roots need about {need_mm:.0f} mm net; {farm.irrigation} irrigation is about {eff*100:.0f}% efficient",
                    "So apply the gross amount. Irrigate in slow, lighter rounds if the soil is dry and hard.")]))
        elif m <= trigger:
            if eff_rain >= 0.6 * need_mm:
                findings.append(Finding("WAIT_FOR_RAIN", WAIT, 1, "Wait - rain should cover the water need",
                    f"Soil is below the trigger ({m:.1f}% vs {trigger:.1f}%), but about {eff_rain:.0f} mm of dependable rain is forecast in 48 h against a need of {need_mm:.0f} mm.",
                    "Re-check tomorrow evening; irrigate if the rain does not arrive",
                    base + [Step("Weather", f"Forecast rain, probability-weighted and discounted for losses: {eff_rain:.0f} mm",
                        "That covers most of the deficit, so irrigating now would waste water and pumping cost.")]))
            else:
                net = max(need_mm - eff_rain, 0.0)
                gross = net / eff
                timing = "Early morning (before 9 am) or after 5 pm"
                if farm.irrigation == "sprinkler" and today.wind_kmh > 20:
                    timing = "Evening, after the wind drops; sprinklers drift above 20 km/h"
                steps = base + [Step("Weather",
                    f"Dependable rain in 48 h: {eff_rain:.0f} mm" if eff_rain else "No dependable rain in the next 48 h",
                    "Rain will not close the gap, so irrigation is needed."),
                    Step("Action", f"Root zone needs {need_mm:.0f} mm net, {gross:.0f} mm gross with {farm.irrigation}",
                         f"That is about {_litres(gross, farm.area_acres):,} litres for {farm.area_acres:g} acre.")]
                findings.append(Finding("IRRIGATE_NOW", IRRIGATE, 2, "Irrigate today",
                    f"Soil is at {m:.1f}%, below the {trigger:.1f}% trigger for {stage.name.lower()}. Apply about {gross:.0f} mm (~{_litres(gross, farm.area_acres):,} litres for {farm.area_acres:g} acre).",
                    timing, steps))
        elif days_to_trigger <= 1.0 and eff_rain < 3:
            findings.append(Finding("IRRIGATE_SOON", IRRIGATE, 1, "Plan to irrigate tomorrow",
                f"Soil is still above the trigger ({m:.1f}% vs {trigger:.1f}%) but will cross it in about {days_to_trigger*24:.0f} hours.",
                "Tomorrow early morning",
                base + [Step("Weather", "No dependable rain in 48 h", "So the drying trend will continue. Get the pump, fuel or power ready.")]))
        else:
            nxt = "more than a month" if days_to_trigger >= 30 else f"{days_to_trigger:.0f} day(s)"
            extra = f" About {eff_rain:.0f} mm of rain is also forecast." if eff_rain >= 3 else ""
            findings.append(Finding("WAIT_OK", WAIT, 0, "Wait - soil has enough water",
                f"Soil is at {m:.1f}%, above the {trigger:.1f}% trigger. At the current drying rate it reaches the trigger in about {nxt}.{extra}",
                f"Re-check in {max(1, int(days_to_trigger // 2))} day(s)",
                base + [Step("Action", "No irrigation needed now", "This saves water and energy, and avoids over-watering that leaches nutrients.")]))
    else:
        findings.append(Finding("WAIT_NO_DATA", WAIT, 0, "Hold irrigation until soil is checked",
            "I will not recommend irrigating on a bad sensor reading.", "After a hand check of the soil",
            [Step("Sensor", "Moisture data unreliable", "Guessing could over- or under-water the crop.")]))

    # ---------------------------------------------------------- 3. weather risks
    hot = [d for d in fdays[:3] if d.tmax_c >= crop.heat_c]
    if hot:
        peak = max(d.tmax_c for d in hot)
        sensitive = stage.name.lower().startswith(("flower", "tassel", "pegging"))
        findings.append(Finding("HEAT_STRESS", ACT, 3 if sensitive and peak >= crop.heat_c + 3 else 2,
            "Heat stress expected",
            f"Up to {peak:.0f} °C is forecast in the next 3 days; {crop.name} suffers above about {crop.heat_c:.0f} °C."
            + (" Flowers and young fruit are at stake." if sensitive else ""),
            "Before the hot days",
            [Step("Weather", f"{len(hot)} of the next 3 days reach {crop.heat_c:.0f} °C or more", "Heat closes leaf pores and can make flowers drop."),
             Step("Crop", f"Stage: {stage.name}", "This stage is heat-sensitive." if sensitive else "Damage is usually smaller at this stage."),
             Step("Action", "Keep soil above the irrigation trigger, irrigate lightly in the evening, mulch if you can.", "Wet, mulched soil stays cooler and roots keep supplying water.")]))
    cold = [d for d in fdays[:3] if d.tmin_c <= crop.cold_c]
    if cold:
        findings.append(Finding("COLD_STRESS", ACT, 2, "Cold nights expected",
            f"Night minimum may drop to {min(d.tmin_c for d in cold):.0f} °C; {crop.name} is stressed below {crop.cold_c:.0f} °C.",
            "Before evening",
            [Step("Weather", "Cold nights forecast", "Growth stalls and young plants can be damaged."),
             Step("Action", "Light irrigation in the evening, and mulch or cover young plants.", "Moist soil releases stored heat through the night.")]))

    dz = crop.disease

    def _matches(hum, tmin, tmax):
        return hum >= dz.min_humidity and tmin <= dz.tmax and tmax >= dz.tmin

    risky = [d for d in fdays[:3] if _matches(d.humidity_pct, d.tmin_c, d.tmax_c)]
    risky_now = 1 if _matches(weather.humidity_pct, weather.temp_c, weather.temp_c) else 0
    if len(risky) + risky_now >= 2:
        wet = any(d.rain_prob >= 0.5 and d.rain_mm >= 2 for d in fdays[:3])
        window = next((d for d in fdays[:4] if d.rain_prob < 0.3 and d.wind_kmh < 15), None)
        win_txt = f"The best dry, calm day to spray is {window.date}." if window else "No calm, dry day is visible in the forecast yet, so scout first."
        findings.append(Finding("DISEASE_RISK", ACT, 2 if wet else 1, f"Conditions favour {dz.name}",
            f"Humid, mild weather (humidity above {dz.min_humidity:.0f}%, {dz.tmin:.0f}-{dz.tmax:.0f} °C) is forecast for several days. {win_txt}",
            "Scout in the next 24 h",
            [Step("Weather", f"{len(risky) + risky_now} of today plus the next 3 days match the {dz.name} pattern", "Leaf wetness and humidity let the disease spread quickly."),
             Step("Crop", f"{crop.name} at {stage.name.lower()} stage", "Check the lower leaves and undersides first."),
             Step("Action", "Walk the field, look for early spots, remove badly affected leaves, improve airflow.",
                  "If spots are spreading, follow your KVK or agriculture officer's advice on what to spray and the dose. Do not spray before rain or in wind above 15 km/h.")]))

    # ---------------------------------------------------------- 4. soil chemistry
    if soil_reading.ph is not None and not (crop.ph_min <= soil_reading.ph <= crop.ph_max):
        low = soil_reading.ph < crop.ph_min
        findings.append(Finding("PH_OFF", ACT, 1, "Soil pH is outside the comfort range",
            f"pH {soil_reading.ph:.1f}; {crop.name} prefers {crop.ph_min:.1f}-{crop.ph_max:.1f}.", "Before the next season",
            [Step("Soil", f"pH {soil_reading.ph:.1f}", "Acidic soil locks up phosphorus and calcium." if low else "Alkaline soil locks up iron, zinc and phosphorus."),
             Step("Action", "Get a lab soil test; it gives the exact amendment rate.",
                  "Usually lime for acidic soil, or gypsum and organic matter for alkaline soil. Sensor pH is only approximate.")]))
    if soil_reading.ec_ds_m is not None and soil_reading.ec_ds_m > crop.ec_max:
        findings.append(Finding("SALINITY", ACT, 1, "Salts are building up in the soil",
            f"EC {soil_reading.ec_ds_m:.1f} dS/m is above the {crop.ec_max:.1f} that {crop.name} tolerates.", "Within a week",
            [Step("Soil", f"EC {soil_reading.ec_ds_m:.1f} dS/m", "Salts pull water away from roots even when the soil looks wet."),
             Step("Action", "If drainage is good, one deeper irrigation flushes salts below the roots. Add organic matter.", "Avoid it on poorly drained fields, where it would raise the water table.")]))
    if soil_reading.n_mg_kg is not None and soil_reading.n_mg_kg < crop.n_low_mg_kg:
        heavy_rain = any(d.rain_mm >= 25 and d.rain_prob >= 0.5 for d in fdays[:2])
        findings.append(Finding("N_LOW", ACT, 1, "Nitrogen looks low",
            f"Sensor nitrogen {soil_reading.n_mg_kg:.0f} mg/kg against a healthy level of about {crop.n_low_mg_kg:.0f} or more.",
            "After the heavy rain passes" if heavy_rain else "This week",
            [Step("Soil", f"Nitrogen {soil_reading.n_mg_kg:.0f} mg/kg", "Low-N crops turn pale from the older leaves up. NPK sensors are rough guides."),
             Step("Weather", "Heavy rain forecast" if heavy_rain else "No heavy rain forecast",
                  "Fertiliser would leach away, so wait." if heavy_rain else "A split top-dressing will be taken up rather than washed out."),
             Step("Action", "Confirm with a soil test or leaf colour chart, then top-dress at the recommended local dose.", "Split doses beat one big dose.")]))

    # ---------------------------------------------------------- 5. choose the primary action
    findings.sort(key=lambda f: (f.severity, _RANK[f.action]), reverse=True)
    primary, others = findings[0], findings[1:]

    # ---------------------------------------------------------- 6. confidence
    if not fdays:
        penalty += 0.2
        notes.append("No forecast available; weather reasoning is limited.")
    if primary.code == "WAIT_FOR_RAIN":
        penalty += 0.10
        notes.append("Decision depends on a rain forecast, which can miss.")
    score = round(max(0.25, min(0.95, 0.93 - penalty)), 2)
    label = "High" if score >= 0.8 else "Medium" if score >= 0.55 else "Low"

    metrics = {
        "moisture_pct": round(m, 1), "trigger_pct": round(trigger, 1),
        "field_capacity_pct": fc, "wilting_point_pct": pwp,
        "depletion_pct": round(depletion * 100), "et0_mm": round(et0, 1), "etc_mm": round(etc, 1),
        "days_to_trigger": None if days_to_trigger >= 30 else round(days_to_trigger, 1),
        "effective_rain_48h_mm": round(eff_rain, 1), "days_after_sowing": das,
        "sensor_age_hours": round(age_h, 1),
    }
    sms = f"KRISHI_PULSE {farm.name}: {primary.title}. {primary.when}."[:160]
    return Advice(asdict(farm), now.isoformat(timespec="minutes"), stage.name, primary, others,
                  {"score": score, "label": label, "notes": notes}, metrics, LABELS, sms)


def advice_to_dict(a: Advice) -> dict:
    return asdict(a)
