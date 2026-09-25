"""A tiny JSON file store standing in for a real database.

Swap this module out for a Postgres/SQLite-backed one later; the rest of the
app only calls the functions below, never touches the file format directly.
"""
from __future__ import annotations
import json, os, threading
from typing import Optional

_LOCK = threading.Lock()
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_FARMS_FILE = os.path.join(_DATA_DIR, "farms.json")
_READINGS_FILE = os.path.join(_DATA_DIR, "readings.json")


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def list_farms() -> list:
    with _LOCK:
        return list(_load(_FARMS_FILE).values())


def get_farm(farm_id: str) -> Optional[dict]:
    with _LOCK:
        return _load(_FARMS_FILE).get(farm_id)


def upsert_farm(farm: dict) -> dict:
    with _LOCK:
        d = _load(_FARMS_FILE)
        d[farm["id"]] = farm
        _save(_FARMS_FILE, d)
        return farm


def delete_farm(farm_id: str) -> bool:
    with _LOCK:
        d = _load(_FARMS_FILE)
        if farm_id not in d:
            return False
        del d[farm_id]
        _save(_FARMS_FILE, d)
        r = _load(_READINGS_FILE)
        r.pop(farm_id, None)
        _save(_READINGS_FILE, r)
        return True


def add_reading(farm_id: str, reading: dict) -> None:
    with _LOCK:
        d = _load(_READINGS_FILE)
        d.setdefault(farm_id, []).append(reading)
        d[farm_id] = d[farm_id][-200:]     # keep recent history bounded
        _save(_READINGS_FILE, d)


def latest_reading(farm_id: str) -> Optional[dict]:
    with _LOCK:
        rows = _load(_READINGS_FILE).get(farm_id, [])
        return rows[-1] if rows else None


def reading_history(farm_id: str, limit: int = 30) -> list:
    with _LOCK:
        return _load(_READINGS_FILE).get(farm_id, [])[-limit:]
