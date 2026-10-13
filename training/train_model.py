"""Entrena un árbol de decisión y lo exporta a JSON para inferencia ligera."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "dataset" / "lecturas_entrenamiento.csv"
OUTPUT = ROOT / "model" / "tree.json"
FEATURES = ["temperatura_c", "vibracion_mm_s"]


def export_node(tree, node_id: int, class_names: list[str]) -> dict:
    left, right = tree.children_left[node_id], tree.children_right[node_id]
    if left == right:
        winner = int(tree.value[node_id][0].argmax())
        return {"type": "leaf", "state": class_names[winner]}
    return {
        "type": "split",
        "feature": FEATURES[int(tree.feature[node_id])],
        "threshold": round(float(tree.threshold[node_id]), 4),
        "left": export_node(tree, left, class_names),
        "right": export_node(tree, right, class_names),
    }


def main() -> None:
    if not DATASET.exists():
        raise FileNotFoundError("Primero ejecute generate_training_data.py")
    data = pd.read_csv(DATASET)
    x_train, x_test, y_train, y_test = train_test_split(
        data[FEATURES], data["estado"], test_size=0.20, random_state=42, stratify=data["estado"]
    )
    model = DecisionTreeClassifier(max_depth=4, min_samples_leaf=8, random_state=42)
    model.fit(x_train, y_train)
    accuracy = accuracy_score(y_test, model.predict(x_test))
    payload = {
        "algorithm": "DecisionTreeClassifier",
        "features": FEATURES,
        "classes": list(model.classes_),
        "test_accuracy": round(float(accuracy), 4),
        "tree": export_node(model.tree_, 0, list(model.classes_)),
        "note": "Modelo académico entrenado con datos sintéticos controlados.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Modelo creado: {OUTPUT}")
    print(f"Exactitud de prueba: {accuracy:.2%}")


if __name__ == "__main__":
    main()
