"""Inferencia ligera, sin scikit-learn en los Workers."""
from __future__ import annotations

import json
from pathlib import Path


class PredictiveModel:
    def __init__(self, tree_path: Path) -> None:
        self.tree_path = tree_path
        self.payload = None
        if tree_path.exists():
            self.payload = json.loads(tree_path.read_text(encoding="utf-8"))

    @property
    def ready(self) -> bool:
        return self.payload is not None

    def predict(self, temperature: float, vibration: float) -> dict:
        if not self.payload:
            return {"state": "MODELO_PENDIENTE", "model_ready": False}
        node = self.payload["tree"]
        values = {"temperatura_c": temperature, "vibracion_mm_s": vibration}
        while node["type"] != "leaf":
            node = node["left"] if values[node["feature"]] <= node["threshold"] else node["right"]
        return {
            "state": node["state"],
            "model_ready": True,
            "algorithm": self.payload["algorithm"],
            "validation_accuracy": self.payload["test_accuracy"],
        }
