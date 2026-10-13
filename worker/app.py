from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter

from flask import Flask, jsonify, request
from model import PredictiveModel

app = Flask(__name__)
ROOT = Path(__file__).resolve().parents[1]
WORKER_ID = os.getenv("WORKER_ID", "edge-worker")
model = PredictiveModel(Path(os.getenv("MODEL_PATH", ROOT / "model" / "tree.json")))


@app.get("/health")
def health():
    return jsonify({"status": "ok", "worker": WORKER_ID, "model_ready": model.ready})


@app.post("/predict")
def predict():
    payload = request.get_json(silent=True) or {}
    try:
        temperature = float(payload["temperatura_c"])
        vibration = float(payload["vibracion_mm_s"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Se requieren temperatura_c y vibracion_mm_s numéricos."}), 400
    started = perf_counter()
    result = model.predict(temperature, vibration)
    result.update({
        "worker": WORKER_ID,
        "temperatura_c": temperature,
        "vibracion_mm_s": vibration,
        "latency_ms": round((perf_counter() - started) * 1000, 3),
    })
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
