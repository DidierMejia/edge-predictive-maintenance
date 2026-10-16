# Fase 2 - Datos reales de Canon G1110

## Propósito

Esta fase crea evidencia de adquisición real y un modelo de **estado operativo**. No atribuye fallas a la impresora ni convierte m/s² a mm/s. El modelo académico previo se conserva como evidencia separada.

## Etiquetas permitidas

| Etiqueta | Cuándo usarla | Qué demuestra |
|---|---|---|
| `normal_reposo` | Impresora encendida, sin imprimir, después de estabilizar el montaje. | Línea base física sin impresión. |
| `normal_impresion` | Impresión ordinaria de 1 a 2 páginas, sin provocar una falla. | Comportamiento físico normal durante trabajo. |

No registrar “Crítico” o “Advertencia” sin una inspección técnica real que lo respalde.

## Protocolo de captura

1. Fijar el ADXL345 con cinta al chasis exterior rígido de la Canon; dejar ESP32 y protoboard fuera de la impresora.
2. Colocar DS18B20 exterior cerca de una zona templada, sin cubrir ventilaciones ni tocar mecanismos, papel o cartuchos.
3. Confirmar antes de cada sesión: `edge-master.service`, `edge-worker.service` y `edge-sensor.service` activos; panel con secuencia que aumenta.
4. Capturar tres sesiones de 10 minutos para cada etiqueta. Mantener el montaje y la orientación sin cambios entre sesiones.
5. En impresión, imprimir únicamente documentos normales. No golpear, sobrecalentar ni bloquear la impresora para simular una falla.
6. Registrar en una nota externa fecha, número de hojas y observaciones del montaje.

La frecuencia actual del ESP32 es aproximadamente una lectura cada 1.7 segundos; por eso una sesión de 10 minutos produce unas 350 lecturas y ventanas suficientes para la primera validación.

## Comandos en edge-master

Copiar `training/phase2_real_data.py` al mismo directorio `training/` del proyecto. Luego:

```bash
cd ~/edge_predictive_maintenance
mkdir -p data/real/raw

# Reposo: ejecutar tres veces (cada vez crea una sesión distinta)
.venv/bin/python training/phase2_real_data.py capture --label normal_reposo --duration 600

# Impresión: iniciar este comando y luego imprimir una o dos páginas normales
.venv/bin/python training/phase2_real_data.py capture --label normal_impresion --duration 600
```

Después de completar las seis sesiones:

```bash
# El entrenamiento pesado se ejecuta en la laptop con .venv-training.
# Primero copiar data/real/ desde el Master a la laptop.
.venv-training/Scripts/python.exe training/phase2_real_data.py build
.venv-training/Scripts/python.exe training/phase2_real_data.py train
```

Los productos son:

- `dataset/lecturas_reales_caracteristicas.csv`: ventanas y métricas reales.
- `model/tree_real.json`: clasificador de estado operativo real.
- `model/baseline_real.json`: rango p05-p95 de operación normal.
- `model/evaluacion_modelo_real.txt`: exactitud de estados operativos, no de fallas.

## Criterio de aceptación

- Cada sesión debe tener al menos 300 lecturas y secuencias continuas.
- Deben existir por lo menos 12 ventanas por cada estado antes de entrenar.
- La validación debe presentarse como “clasificación reposo/impresión” y no como diagnóstico de daño.
- Si se mueve el sensor, se cambia su orientación o se modifica el montaje, se debe comenzar una nueva línea base.
