"""KRISHI_PULSE web app: a small Flask server exposing a JSON API and a dashboard UI."""
from __future__ import annotations
import os, uuid
from datetime import datetime

from flask import Flask, jsonify, request, render_template, abort

from .knowledge import CROPS, SOILS, pest_harm, pests_for
from .models import Farm, SoilReading, Weather
from .engine import advise, advice_to_dict, detect_pests
from .weather_client import fetch_weather
from . import store

APP_DIR = os.path.dirname(__file__)
app = Flask(__name__, template_folder=os.path.join(APP_DIR, "..", "templates"),
            static_folder=os.path.join(APP_DIR, "..", "static"))


def _catalog():
    return {
        "crops": [{"key": k, "name": c.name} for k, c in CROPS.items()],
        "soils": [{"key": k, "name": s.name} for k, s in SOILS.items()],
        "irrigation": ["drip", "sprinkler", "furrow", "flood"],
    }


@app.get("/")
def index():
    return render_template("index.html", catalog=_catalog(), farms=store.list_farms())


@app.get("/api/catalog")
def api_catalog():
    return jsonify(_catalog())


@app.get("/api/pests")
def api_pests():
    crop_key = request.args.get("crop", "")
    if crop_key not in CROPS:
        return jsonify({"error": "choose a supported crop"}), 400
    return jsonify({"crop": crop_key, "pests": [
        {"key": pest.key, "name": pest.name, "symptoms": list(pest.symptoms), "harm": pest_harm(pest.key)}
        for pest in pests_for(crop_key)
    ]})


@app.post("/api/pest-detection")
def api_pest_detection():
    body = request.get_json(force=True) or {}
    crop_key = body.get("crop")
    symptoms = body.get("symptoms") or []
    if crop_key not in CROPS:
        return jsonify({"error": "choose a supported crop"}), 400
    if not isinstance(symptoms, list) or not symptoms:
        return jsonify({"error": "select at least one field sign"}), 400
    return jsonify(detect_pests(crop_key, symptoms, body.get("notes", "")))


@app.get("/api/farms")
def api_list_farms():
    return jsonify(store.list_farms())


@app.post("/api/farms")
def api_create_farm():
    body = request.get_json(force=True) or {}
    if body.get("crop") not in CROPS:
        return jsonify({"error": f"unknown crop '{body.get('crop')}'"}), 400
    if body.get("soil_type") not in SOILS:
        return jsonify({"error": f"unknown soil_type '{body.get('soil_type')}'"}), 400
    body["id"] = body.get("id") or uuid.uuid4().hex[:10]
    farm = Farm.from_dict(body)
    store.upsert_farm(farm.__dict__)
    return jsonify(farm.__dict__), 201


@app.delete("/api/farms/<farm_id>")
def api_delete_farm(farm_id):
    ok = store.delete_farm(farm_id)
    if not ok:
        abort(404)
    return jsonify({"deleted": farm_id})


@app.post("/api/farms/<farm_id>/readings")
def api_add_reading(farm_id):
    if not store.get_farm(farm_id):
        abort(404)
    body = request.get_json(force=True) or {}
    body["ts"] = body.get("ts") or datetime.now().isoformat(timespec="minutes")
    reading = SoilReading.from_dict(body)
    store.add_reading(farm_id, reading.__dict__)
    return jsonify(reading.__dict__), 201


@app.get("/api/farms/<farm_id>/history")
def api_history(farm_id):
    if not store.get_farm(farm_id):
        abort(404)
    return jsonify(store.reading_history(farm_id))


@app.get("/api/farms/<farm_id>/advice")
def api_advice(farm_id):
    farm_d = store.get_farm(farm_id)
    if not farm_d:
        abort(404)
    reading_d = store.latest_reading(farm_id)
    if not reading_d:
        return jsonify({"error": "no soil reading yet for this farm"}), 409
    farm = Farm.from_dict(farm_d)
    reading = SoilReading.from_dict(reading_d)
    weather = fetch_weather(farm.lat, farm.lon)
    result = advise(farm, reading, weather)
    return jsonify(advice_to_dict(result))


@app.errorhandler(404)
def not_found(_e):
    return jsonify({"error": "not found"}), 404


def create_app():
    return app


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
