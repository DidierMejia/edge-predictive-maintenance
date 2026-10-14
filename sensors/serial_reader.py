"""Recibe lecturas JSON del ESP32 y publica una ventana local para el Master."""
from __future__ import annotations

import json
import math
import os
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parents[1]
PORT = os.environ.get(
    "EDGE_SENSOR_PORT", "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
)
SNAPSHOT = ROOT / "runtime" / "sensor_latest.json"


def valid(reading):
    if not isinstance(reading, dict) or reading.get("tipo") != "lectura":
        return False
    if reading.get("dispositivo") != "edge-sensor-01":
        return False
    seq = reading.get("secuencia")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        return False
    for key in ("ax_m_s2", "ay_m_s2", "az_m_s2"):
        value = reading.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            return False
    if reading.get("temperatura_ok") is not True:
        return reading.get("temperatura_c") is None
    value = reading.get("temperatura_c")
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and -55 <= value <= 125)


def publish(samples):
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    temporary = SNAPSHOT.with_suffix(".tmp")
    temporary.write_text(json.dumps({"readings": list(samples)}, ensure_ascii=False), encoding="utf-8")
    temporary.replace(SNAPSHOT)


def main():
    samples = deque(maxlen=20)
    while True:
        try:
            with serial.Serial(PORT, 115200, timeout=2, exclusive=True) as device:
                print(f"ESP32 conectado: {PORT}", flush=True)
                device.reset_input_buffer()
                while True:
                    raw = device.readline(2048)
                    if not raw.endswith(b"\n"):
                        continue
                    try:
                        reading = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, ValueError):
                        continue
                    if not valid(reading):
                        continue
                    samples.append({
                        "fecha_recepcion_utc": datetime.now(timezone.utc).isoformat(),
                        "lectura": reading,
                    })
                    publish(samples)
        except (serial.SerialException, OSError) as error:
            print(f"Esperando ESP32: {error}", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
