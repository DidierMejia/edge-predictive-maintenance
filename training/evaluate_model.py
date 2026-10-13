import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_model import FEATURES, export_node

ROOT = Path(__file__).resolve().parents[1]
data = pd.read_csv(
    ROOT / "dataset" / "lecturas_entrenamiento.csv",
    encoding="utf-8"
)
exportado = json.loads(
    (ROOT / "model" / "tree.json").read_text(encoding="utf-8")
)

x_train, x_test, y_train, y_test = train_test_split(
    data[FEATURES],
    data["estado"],
    test_size=0.20,
    random_state=42,
    stratify=data["estado"]
)

modelo = DecisionTreeClassifier(
    max_depth=4,
    min_samples_leaf=8,
    random_state=42
)
modelo.fit(x_train, y_train)
clases = list(modelo.classes_)

arbol = export_node(modelo.tree_, 0, clases)
if arbol != exportado["tree"] or clases != exportado["classes"]:
    raise SystemExit(
        "El modelo reconstruido no coincide con tree.json. "
        "No se modifico el modelo. Compartir este mensaje antes de continuar."
    )

predicciones = modelo.predict(x_test)

from worker.model import PredictiveModel
modelo_json = PredictiveModel(ROOT / "model" / "tree.json")
predicciones_json = [
    modelo_json.predict(
        float(fila["temperatura_c"]),
        float(fila["vibracion_mm_s"])
    )["state"]
    for _, fila in x_test.iterrows()
]

matriz = pd.DataFrame(
    confusion_matrix(y_test, predicciones_json, labels=clases),
    index=clases,
    columns=clases
)
matriz.index.name = "Estado real"
matriz.columns.name = "Estado predicho"

detalle = x_test.copy()
detalle.insert(0, "indice_dataset", x_test.index)
detalle["estado_real"] = y_test
detalle["prediccion_sklearn"] = predicciones
detalle["prediccion_json"] = predicciones_json
detalle["correcto"] = detalle["estado_real"] == detalle["prediccion_json"]

carpeta = ROOT / "evidencias" / (
    "evaluacion_modelo_" +
    datetime.now().strftime("%Y%m%d_%H%M%S_%f")
)
carpeta.mkdir(parents=True)

matriz.to_csv(carpeta / "matriz_confusion.csv", encoding="utf-8-sig")
detalle.to_csv(
    carpeta / "predicciones_prueba.csv",
    index=False,
    encoding="utf-8-sig"
)

reporte = classification_report(
    y_test,
    predicciones_json,
    labels=clases,
    digits=3,
    zero_division=0
)

resumen = {
    "total_lecturas": len(data),
    "entrenamiento": len(x_train),
    "prueba": len(x_test),
    "aciertos_json": int(detalle["correcto"].sum()),
    "errores_json": int((~detalle["correcto"]).sum()),
    "exactitud_sklearn": float(accuracy_score(y_test, predicciones)),
    "exactitud_json": float(accuracy_score(y_test, predicciones_json)),
    "diferencias_sklearn_json": int(
        (detalle["prediccion_sklearn"] != detalle["prediccion_json"]).sum()
    ),
    "clases": clases
}
(carpeta / "resumen.json").write_text(
    json.dumps(resumen, ensure_ascii=False, indent=2),
    encoding="utf-8"
)
(carpeta / "reporte_clasificacion.txt").write_text(
    reporte, encoding="utf-8"
)

print("\n--- RESUMEN ---")
print(json.dumps(resumen, ensure_ascii=False, indent=2))
print("\n--- MATRIZ: FILAS REALES / COLUMNAS PREDICHAS ---")
print(matriz.to_string())
print("\n--- RESULTADOS POR CLASE ---")
print(reporte)
print("\nEvidencias:", carpeta)

