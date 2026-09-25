# KRISHI_PULSE

**Smart Farm Decision Support** — reads soil, weather, crop and sensor data
together and tells a smallholder farmer what to do next: **irrigate, wait,
or act on a risk** — with the reasoning shown, in plain language.

Built by Preetham Acharya DR.

> KRISHI_PULSE is not a weather app or a sensor dashboard. It fuses live
> weather, a farm's soil/crop profile, and the latest sensor (or hand-check)
> reading into **one** stated action, with a stated time window, backed by an
> auditable reasoning trail and a confidence score.

---

## How this meets the brief

| Brief requirement | Where it lives |
|---|---|
| **Farm & crop profile** — crop, growth stage, plot details | `krishi_pulse/models.py::Farm`, growth-stage lookup in `engine.stage_for()`, form on the dashboard |
| **Field-condition monitoring** — real-time or simulated readings | `krishi_pulse/models.py::SoilReading`, `POST /api/farms/<id>/readings`, "Field-condition monitoring" panel |
| **Two or more data sources** | Soil sensor (`SoilReading`) + live weather (`weather_client.py`, Open-Meteo) + a static agronomy knowledge base (`knowledge.py`) — three sources, fused together |
| **Risk & need identification** | `engine.advise()` checks water stress, waterlogging, heat/cold stress, disease-favourable weather, pH, salinity and low nitrogen |
| **Intelligent recommendation** — a specific operation, with a time window | `Finding.title` / `.detail` / `.when`, rendered as the big "verdict" card |
| **Explained reasoning** — why this advice, and how confident | `Finding.steps` (a numbered Soil → Crop → Weather → Action ledger) plus `Advice.confidence` (score, label, data-quality notes) |
| **History & alerts** | `GET /api/farms/<id>/history` + moisture trend chart; lower-priority `Finding`s render as alert cards under the main verdict |
| **Working prototype: data → assessment → risk → decision** | End to end: log a reading → `engine.advise()` assesses water balance & risks → ranks findings → returns one primary decision |
| **Usable on low/patchy connectivity** | Weather has an offline synthetic fallback (`weather_client._synthetic`) if the network call fails; storage is a local JSON file, no external DB required; UI is a single lightweight page |

## The decision logic, briefly

1. **Water balance.** Soil field capacity and wilting point (by soil type) plus
   the crop's growth-stage water need (crop coefficient × reference ET, via the
   Hargreaves equation from daily temperature) give a moisture *trigger* level.
   Below it → irrigate (with the mm/litres to apply); near saturation →
   waterlogging risk; forecast rain that would cover the deficit → wait.
2. **Sensor sanity.** Impossible readings, stale data, and suspicious jumps are
   caught and downgrade confidence *before* they can drive a bad recommendation.
3. **Weather risk.** Forecast heat/cold stress and disease-favourable
   humidity/temperature windows for the crop's known disease pressure.
4. **Soil chemistry.** pH, EC (salinity) and nitrogen are checked against the
   crop's tolerance if the sensor reports them.
5. **Ranking.** All findings are sorted by severity; the top one becomes the
   primary IRRIGATE / WAIT / ACT decision, the rest show as secondary alerts.
6. **Confidence.** Starts high and is discounted for stale/invalid sensor data,
   a missing forecast, or a decision that leans on an uncertain rain forecast.

This is a transparent **rule-based expert system**, not a black-box model —
deliberately, so every recommendation can be explained and checked, which
matters when the "user" is deciding whether to spend money on irrigation.

## Project layout

```
KRISHI_PULSE/
├── krishi_pulse/
│   ├── models.py          # Farm, SoilReading, Weather, ForecastDay (data shapes)
│   ├── knowledge.py       # Soil + crop agronomy reference data
│   ├── engine.py          # The decision engine (advise())
│   ├── weather_client.py  # Live weather (Open-Meteo) + offline fallback
│   ├── store.py           # Small JSON file store (swap for a real DB later)
│   └── app.py             # Flask app: REST API + dashboard route
├── templates/index.html   # Single-page dashboard (vanilla JS, no build step)
├── static/style.css       # Design system
├── tests/                 # unittest suite (engine + API)
├── data/                  # farms.json / readings.json (created at runtime)
├── seed_demo.py           # Populates two demo farms with sample readings
├── run.py                 # python run.py -> http://localhost:5000
└── requirements.txt
```

## Running it

```bash
pip install -r requirements.txt
python seed_demo.py     # optional: adds two demo farms so the dashboard isn't empty
python run.py            # -> http://localhost:5000
```

## REST API

| Method & path | What it does |
|---|---|
| `GET /api/catalog` | Supported crops, soil types, irrigation methods |
| `GET /api/farms` | List farms |
| `POST /api/farms` | Create a farm profile |
| `DELETE /api/farms/<id>` | Remove a farm |
| `POST /api/farms/<id>/readings` | Log a soil/sensor reading |
| `GET /api/farms/<id>/history` | Recent readings (for the trend chart) |
| `GET /api/farms/<id>/advice` | Today's decision: primary action, alerts, reasoning, confidence |

Example:
```bash
curl -X POST localhost:5000/api/farms -H "Content-Type: application/json" -d '{
  "name": "North field", "crop": "tomato", "soil_type": "red_loam",
  "sowing_date": "2026-08-10", "area_acres": 1.5, "irrigation": "drip"
}'
```

## Testing

```bash
python -m unittest discover -s tests -v
```
14 tests cover the water-balance logic, sensor-fault handling, heat/disease
risk detection, growth-stage lookup and the full create-farm → log-reading →
get-advice API flow.

## Extending it

- **More crops/soils:** add entries to `knowledge.py` — no engine code changes needed.
- **Real sensors:** point an IoT gateway at `POST /api/farms/<id>/readings`.
- **Real database:** the app never touches JSON directly — swap `store.py`'s
  functions for SQLAlchemy/Postgres calls and nothing else changes.
- **SMS/IVR delivery:** `Advice.sms` already renders a ≤160-char SMS-ready summary.
- **ML layer later:** the rule-based engine can stay as an explainable baseline
  and fallback even if a learned model is added on top.
