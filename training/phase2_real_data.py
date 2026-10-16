"""Fase 2: captura, preparación y entrenamiento con lecturas reales.

No convierte aceleración (m/s²) en velocidad de vibración (mm/s) de forma
artificial. La primera versión aprende estados operativos reales de la Canon:
normal_reposo y normal_impresion. Las métricas de desviación se conservan para
una fase posterior de detección de anomalías.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "real" / "raw"
DATASET = ROOT / "dataset" / "lecturas_reales_caracteristicas.csv"
MODEL = ROOT / "model" / "tree_real.json"
BASELINE = ROOT / "model" / "baseline_real.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def valid_reading(reading: dict) -> bool:
    if not isinstance(reading, dict) or reading.get("tipo") != "lectura":
        return False
    if reading.get("temperatura_ok") is not True or not finite_number(reading.get("temperatura_c")):
        return False
    return all(finite_number(reading.get(key)) for key in ("ax_m_s2", "ay_m_s2", "az_m_s2"))


def load_snapshot(path: Path) -> list[dict]:
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
        samples = content.get("readings", [])
        return samples if isinstance(samples, list) else []
    except (OSError, ValueError, TypeError):
        return []


def capture(args: argparse.Namespace) -> None:
    """Guarda una sesión sin abrir el puerto serial (el servicio ya lo posee)."""
    snapshot = Path(args.snapshot)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"{stamp}_{args.label}"
    folder = Path(args.output_dir) / session_id
    folder.mkdir(parents=True, exist_ok=False)
    readings_file = folder / "readings.jsonl"
    metadata = {
        "session_id": session_id,
        "label": args.label,
        "purpose": args.purpose,
        "printer": args.printer,
        "mounting": args.mounting,
        "operator": args.operator,
        "started_utc": utc_now(),
        "requested_duration_s": args.duration,
        "source_snapshot": str(snapshot),
        "sampling_note": "Se deduplican las secuencias publicadas por edge-sensor.service.",
    }
    seen: set[tuple[str, int]] = set()
    accepted = 0
    started = time.monotonic()
    print(f"Capturando {args.duration}s: {session_id}", flush=True)
    with readings_file.open("w", encoding="utf-8") as output:
        while time.monotonic() - started < args.duration:
            for sample in load_snapshot(snapshot):
                reading = sample.get("lectura") if isinstance(sample, dict) else None
                if not valid_reading(reading):
                    continue
                key = (str(reading.get("dispositivo", "")), int(reading.get("secuencia", -1)))
                if key in seen:
                    continue
                seen.add(key)
                row = {
                    "fecha_recepcion_utc": sample.get("fecha_recepcion_utc", utc_now()),
                    "lectura": reading,
                }
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
                output.flush()
                accepted += 1
                print(f"{accepted:04d} | secuencia {reading['secuencia']} | {reading['temperatura_c']:.2f} °C", flush=True)
            time.sleep(args.interval)
    metadata["finished_utc"] = utc_now()
    metadata["accepted_readings"] = accepted
    (folder / "session.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if accepted == 0:
        raise SystemExit("No se recibieron lecturas. Verifique edge-sensor.service y runtime/sensor_latest.json.")
    print(f"Sesión guardada: {folder} ({accepted} lecturas)")


def read_session(folder: Path) -> tuple[dict, list[dict]]:
    metadata = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    rows: list[dict] = []
    for line in (folder / "readings.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            sample = json.loads(line)
            reading = sample["lectura"]
            if valid_reading(reading):
                rows.append({"fecha_recepcion_utc": sample.get("fecha_recepcion_utc"), **reading})
        except (ValueError, KeyError, TypeError):
            continue
    return metadata, rows


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def standard_deviation(values: list[float]) -> float:
    average = mean(values)
    return math.sqrt(sum((item - average) ** 2 for item in values) / len(values))


def features_for_window(rows: list[dict], metadata: dict) -> dict:
    temp = [float(row["temperatura_c"]) for row in rows]
    x = [float(row["ax_m_s2"]) for row in rows]
    y = [float(row["ay_m_s2"]) for row in rows]
    z = [float(row["az_m_s2"]) for row in rows]
    magnitude = [math.sqrt(a * a + b * b + c * c) for a, b, c in zip(x, y, z)]
    # La variabilidad del módulo elimina el efecto de la gravedad estática.
    dynamic = [item - mean(magnitude) for item in magnitude]
    return {
        "session_id": metadata["session_id"],
        "estado_operativo": metadata["label"],
        "muestras_ventana": len(rows),
        "temperatura_promedio_c": round(mean(temp), 5),
        "temperatura_delta_c": round(temp[-1] - temp[0], 5),
        "aceleracion_modulo_promedio_m_s2": round(mean(magnitude), 5),
        "aceleracion_desviacion_m_s2": round(standard_deviation(magnitude), 5),
        "aceleracion_dinamica_rms_m_s2": round(math.sqrt(mean([item * item for item in dynamic])), 5),
        "ax_desviacion_m_s2": round(standard_deviation(x), 5),
        "ay_desviacion_m_s2": round(standard_deviation(y), 5),
        "az_desviacion_m_s2": round(standard_deviation(z), 5),
    }


def build_dataset(args: argparse.Namespace) -> None:
    raw_root = Path(args.raw_dir)
    rows: list[dict] = []
    ignored: list[str] = []
    for folder in sorted(raw_root.iterdir()) if raw_root.exists() else []:
        if not folder.is_dir() or not (folder / "session.json").exists() or not (folder / "readings.jsonl").exists():
            continue
        try:
            metadata, samples = read_session(folder)
        except (OSError, ValueError, TypeError) as error:
            ignored.append(f"{folder.name}: {error}")
            continue
        if len(samples) < args.window:
            ignored.append(f"{folder.name}: solo {len(samples)} lecturas")
            continue
        for start in range(0, len(samples) - args.window + 1, args.stride):
            rows.append(features_for_window(samples[start:start + args.window], metadata))
    if not rows:
        raise SystemExit("No se generaron ventanas. Capture al menos una sesión con suficientes lecturas.")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with output.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Dataset real creado: {output} ({len(rows)} ventanas)")
    print("Ventanas por estado:", dict(Counter(row["estado_operativo"] for row in rows)))
    if ignored:
        print("Sesiones no usadas:", "; ".join(ignored))


FEATURES = [
    "temperatura_promedio_c", "temperatura_delta_c", "aceleracion_modulo_promedio_m_s2",
    "aceleracion_desviacion_m_s2", "aceleracion_dinamica_rms_m_s2",
    "ax_desviacion_m_s2", "ay_desviacion_m_s2", "az_desviacion_m_s2",
]


def export_node(tree, node_id: int, class_names: list[str]) -> dict:
    left, right = tree.children_left[node_id], tree.children_right[node_id]
    if left == right:
        return {"type": "leaf", "state": class_names[int(tree.value[node_id][0].argmax())]}
    return {
        "type": "split",
        "feature": FEATURES[int(tree.feature[node_id])],
        "threshold": round(float(tree.threshold[node_id]), 6),
        "left": export_node(tree, left, class_names),
        "right": export_node(tree, right, class_names),
    }


def quantile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    lower, upper = math.floor(index), math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def train(args: argparse.Namespace) -> None:
    try:
        import pandas as pd
        from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
        from sklearn.model_selection import train_test_split
        from sklearn.tree import DecisionTreeClassifier
    except ImportError as error:
        raise SystemExit(f"Falta una dependencia de entrenamiento: {error}. Instale training/requirements.txt.")
    data = pd.read_csv(args.dataset, encoding="utf-8-sig")
    counts = data["estado_operativo"].value_counts()
    if len(counts) < 2:
        raise SystemExit("Se requieren al menos dos estados operativos reales para entrenar.")
    if int(counts.min()) < args.min_windows:
        raise SystemExit(f"Cada estado necesita al menos {args.min_windows} ventanas. Actual: {counts.to_dict()}")
    x_train, x_test, y_train, y_test = train_test_split(
        data[FEATURES], data["estado_operativo"], test_size=args.test_size,
        random_state=42, stratify=data["estado_operativo"],
    )
    model = DecisionTreeClassifier(max_depth=3, min_samples_leaf=3, random_state=42)
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)
    classes = list(model.classes_)
    model_path = Path(args.model)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "algorithm": "DecisionTreeClassifier",
        "purpose": "Clasificación de estado operativo real; no diagnostica fallas mecánicas.",
        "source": "Sesiones etiquetadas de Canon G1110 con ESP32, DS18B20 y ADXL345.",
        "features": FEATURES,
        "classes": classes,
        "test_accuracy": round(float(accuracy_score(y_test, predicted)), 4),
        "training_windows": int(len(x_train)),
        "test_windows": int(len(x_test)),
        "tree": export_node(model.tree_, 0, classes),
    }
    model_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    baseline_rows = data[data["estado_operativo"].astype(str).str.startswith("normal_")]
    baseline = {
        "purpose": "Rango empírico de operación normal. Superarlo requiere revisión, no constituye diagnóstico automático.",
        "source_windows": int(len(baseline_rows)),
        "features": {
            key: {"p05": round(quantile(list(baseline_rows[key]), 0.05), 6),
                  "p95": round(quantile(list(baseline_rows[key]), 0.95), 6)}
            for key in FEATURES
        },
    }
    Path(args.baseline).write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence = model_path.parent / "evaluacion_modelo_real.txt"
    evidence.write_text(
        "Exactitud de clasificación de estado operativo: " + f"{payload['test_accuracy']:.2%}\n\n" +
        "Matriz de confusión (filas reales / columnas predichas):\n" +
        str(confusion_matrix(y_test, predicted, labels=classes)) + "\n\n" +
        classification_report(y_test, predicted, labels=classes, digits=3, zero_division=0),
        encoding="utf-8",
    )
    print(json.dumps({"accuracy": payload["test_accuracy"], "classes": classes,
                      "model": str(model_path), "baseline": str(args.baseline)}, ensure_ascii=False, indent=2))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    capture_p = commands.add_parser("capture", help="Capturar una sesión desde el snapshot del ESP32")
    capture_p.add_argument("--label", choices=["normal_reposo", "normal_impresion"], required=True)
    capture_p.add_argument("--duration", type=int, default=600, help="segundos; 600 recomendado")
    capture_p.add_argument("--snapshot", default=str(ROOT / "runtime" / "sensor_latest.json"))
    capture_p.add_argument("--output-dir", default=str(RAW_ROOT))
    capture_p.add_argument("--interval", type=float, default=0.25)
    capture_p.add_argument("--printer", default="Canon G1110")
    capture_p.add_argument("--mounting", default="ADXL345 fijo al chasis exterior; DS18B20 exterior sin obstruir ventilación")
    capture_p.add_argument("--operator", default="Didier Mejía")
    capture_p.add_argument("--purpose", default="Línea base real de operación normal")
    capture_p.set_defaults(func=capture)
    build_p = commands.add_parser("build", help="Construir ventanas y características")
    build_p.add_argument("--raw-dir", default=str(RAW_ROOT))
    build_p.add_argument("--output", default=str(DATASET))
    build_p.add_argument("--window", type=int, default=10, help="lecturas por ventana (~17 s)")
    build_p.add_argument("--stride", type=int, default=5, help="salto entre ventanas")
    build_p.set_defaults(func=build_dataset)
    train_p = commands.add_parser("train", help="Entrenar árbol de estados operativos reales")
    train_p.add_argument("--dataset", default=str(DATASET))
    train_p.add_argument("--model", default=str(MODEL))
    train_p.add_argument("--baseline", default=str(BASELINE))
    train_p.add_argument("--test-size", type=float, default=0.25)
    train_p.add_argument("--min-windows", type=int, default=12)
    train_p.set_defaults(func=train)
    return result


if __name__ == "__main__":
    args = parser().parse_args()
    args.func(args)
