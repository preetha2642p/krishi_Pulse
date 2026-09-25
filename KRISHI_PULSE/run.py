#!/usr/bin/env python3
"""Entry point: python run.py  (then open http://localhost:5001)"""
from krishi_pulse.app import app

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
