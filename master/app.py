from __future__ import annotations

import json
import csv
from datetime import datetime, timezone
from threading import Lock
from itertools import cycle
from pathlib import Path
from time import perf_counter

import requests
from flask import Flask, jsonify, render_template_string, request

ROOT = Path(__file__).resolve().parents[1]
WORKERS = json.loads((ROOT / "config" / "nodes.json").read_text())["workers"]
ROUND_ROBIN = cycle(WORKERS)
app = Flask(__name__)

PAGE = """<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Edge Maintenance - Piedrasanta</title>
<style>body{font-family:Arial;max-width:820px;margin:35px auto;background:#f4f6f8;color:#17233c}h1{color:#17365d}.box{background:#fff;padding:20px;border-radius:12px;margin:14px 0;box-shadow:0 2px 8px #ccd}input,button{padding:10px;margin:5px;font-size:16px}button{background:#17365d;color:#fff;border:0;border-radius:6px}pre{white-space:pre-wrap}</style></head>
<body><h1>Mantenimiento Predictivo Edge</h1><p>Litografía Editorial Piedrasanta - inferencia local sin nube.</p>
<div class='box'><b>Lectura de prueba</b><br>Temperatura °C <input id='temp' type='number' value='45' step='0.1'> Vibración mm/s <input id='vib' type='number' value='2.1' step='0.1'><button onclick='analyze()'>Analizar</button><br><button onclick="preset(45,2.1)">Normal</button><button onclick="preset(73,6.2)">Advertencia</button><button onclick="preset(91,9.8)">Crítico</button></div>
<div class='box'><b>Resultado</b><pre id='result'>Esperando lectura...</pre></div><div class='box'><b>Workers</b><pre id='workers'></pre></div>
<script>function preset(t,v){temp.value=t;vib.value=v;analyze()}async function analyze(){let r=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({temperatura_c:+temp.value,vibracion_mm_s:+vib.value})});result.textContent=JSON.stringify(await r.json(),null,2);status()}async function status(){workers.textContent=JSON.stringify(await (await fetch('/api/status')).json(),null,2)}status()</script></body></html>"""


def status(worker: dict) -> dict:
    try:
        response = requests.get(f"{worker['url']}/health", timeout=2)
        return {**worker, "available": response.ok, "detail": response.json() if response.ok else response.text}
    except requests.RequestException as error:
        return {**worker, "available": False, "detail": str(error)}


def distribute(payload: dict):
    skipped = []
    for _ in range(len(WORKERS)):
        worker = next(ROUND_ROBIN)
        if not status(worker)["available"]:
            skipped.append(worker["id"])
            continue
        try:
            started = perf_counter()
            response = requests.post(f"{worker['url']}/predict", json=payload, timeout=5)
            response.raise_for_status()
            answer = response.json()
            answer["cluster_latency_ms"] = round((perf_counter() - started) * 1000, 3)
            answer["skipped_workers"] = skipped
            return answer, 200
        except requests.RequestException:
            skipped.append(worker["id"])
    return {"error": "No hay Workers disponibles.", "skipped_workers": skipped}, 503



HISTORIAL = ROOT / "evidencias" / "historial_lecturas.csv"
HISTORIAL_LOCK = Lock()
SENSOR_SNAPSHOT = ROOT / "runtime" / "sensor_latest.json"


def guardar_historial(payload, answer, code):
    campos = [
        "fecha_utc", "temperatura_c", "vibracion_mm_s",
        "estado", "worker", "latencia_worker_ms",
        "http_status", "error"
    ]
    fila = {
        "fecha_utc": datetime.now(timezone.utc).isoformat(),
        "temperatura_c": payload["temperatura_c"],
        "vibracion_mm_s": payload["vibracion_mm_s"],
        "estado": answer.get("state", ""),
        "worker": answer.get("worker", ""),
        "latencia_worker_ms": answer.get("cluster_latency_ms", ""),
        "http_status": code,
        "error": answer.get("error", "")
    }
    with HISTORIAL_LOCK:
        HISTORIAL.parent.mkdir(parents=True, exist_ok=True)
        nuevo = not HISTORIAL.exists() or HISTORIAL.stat().st_size == 0
        with HISTORIAL.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=campos)
            if nuevo:
                writer.writeheader()
            writer.writerow(fila)

@app.get("/")
def dashboard():
    return render_template_string((ROOT / "master" / "panel.html").read_text(encoding="utf-8"))



@app.get("/api/history")
def api_history():
    from collections import deque
    try:
        with HISTORIAL_LOCK:
            if not HISTORIAL.exists():
                return jsonify({"readings": []})
            with HISTORIAL.open(newline="", encoding="utf-8-sig") as f:
                filas = list(deque(csv.DictReader(f), maxlen=20))
        return jsonify({"readings": list(reversed(filas))})
    except (OSError, csv.Error, UnicodeError):
        app.logger.exception("No se pudo leer el historial")
        return jsonify({"error": "No se pudo leer el historial"}), 500

@app.get("/api/status")
def api_status():
    return jsonify({"workers": [status(worker) for worker in WORKERS]})


@app.get("/api/sensor")
def api_sensor():
    """Muestras reales del ESP32; no alimentan el modelo sintético."""
    try:
        data = json.loads(SENSOR_SNAPSHOT.read_text(encoding="utf-8"))
        readings = data["readings"]
        if not isinstance(readings, list) or not readings:
            raise ValueError("Sin lecturas")
        seen = datetime.fromisoformat(readings[-1]["fecha_recepcion_utc"])
        if seen.tzinfo is None:
            raise ValueError("Fecha sin zona horaria")
        age = max(0, (datetime.now(timezone.utc) - seen).total_seconds())
        return jsonify({"connected": age <= 10, "age_s": round(age, 1),
                        "readings": readings[-20:]})
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return jsonify({"connected": False, "age_s": None, "readings": []})


@app.post("/api/analyze")
def analyze():
    from math import isfinite

    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"error": "Envíe un objeto JSON con temperatura y vibración."}), 400

    payload = {}
    try:
        for campo in ("temperatura_c", "vibracion_mm_s"):
            valor = datos[campo]
            if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
                raise ValueError("Tipo inválido")
            numero = float(valor)
            if not isfinite(numero):
                raise ValueError("Valor no finito")
            payload[campo] = numero
    except (KeyError, TypeError, ValueError, OverflowError):
        return jsonify({"error": "Ingrese temperatura y vibración numéricas y finitas."}), 400

    if payload["vibracion_mm_s"] < 0:
        return jsonify({"error": "La vibración no puede ser negativa."}), 400

    answer, code = distribute(payload)
    try:
        guardar_historial(payload, answer, code)
        answer["historial_guardado"] = True
    except OSError:
        app.logger.exception("No se pudo guardar el historial")
        answer["historial_guardado"] = False
    return jsonify(answer), code


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
