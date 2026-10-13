"""Genera lecturas sintéticas reproducibles para el prototipo académico."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
OUTPUT = Path(__file__).resolve().parents[1] / "dataset" / "lecturas_entrenamiento.csv"


def readings(label: str, count: int, temperature: tuple[float, float], vibration: tuple[float, float]) -> pd.DataFrame:
    return pd.DataFrame({
        "temperatura_c": rng.uniform(*temperature, count).round(2),
        "vibracion_mm_s": rng.uniform(*vibration, count).round(2),
        "estado": label,
    })


def main() -> None:
    # Rangos de demostración, no sustituyen diagnóstico de un fabricante.
    data = pd.concat([
        readings("Normal", 180, (35, 62), (1.0, 4.4)),
        readings("Advertencia", 160, (58, 80), (3.8, 7.2)),
        readings("Crítico", 160, (76, 98), (6.5, 11.0)),
    ], ignore_index=True).sample(frac=1, random_state=42)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(OUTPUT, index=False)
    print(f"Datos creados: {OUTPUT} ({len(data)} lecturas)")


if __name__ == "__main__":
    main()
