# Mantenimiento Predictivo con Edge Computing
## Prototipo académico — Editorial Piedrasanta

Proyecto de Arquitectura de Computadoras II de la Universidad Mariano Gálvez de Guatemala.

Clasifica lecturas de temperatura y vibración como **Normal**, **Advertencia** o **Crítico**, mediante un árbol de decisión ejecutado localmente.

El caso de referencia es una guillotina industrial. Las lecturas utilizadas son simuladas y el modelo fue entrenado con datos sintéticos. El prototipo clasifica condiciones actuales; su capacidad para predecir fallas futuras no ha sido validada.

## Arquitectura implementada

| Equipo | Servicio | Dirección utilizada en las pruebas |
|---|---|---|
| edge-master | Master: panel, distribución e historial | 192.168.0.17:8000 |
| edge-master | Worker local: inferencia | 127.0.0.1:5000 |
| edge-worker1 | Worker remoto: inferencia | 192.168.0.36:5000 |

Dos equipos físicos ejecutan un Master y dos Workers. Las direcciones corresponden al entorno de prueba y deben adaptarse al instalar el proyecto.

El Master alterna solicitudes entre Workers, omite los que no responden y devuelve HTTP 503 cuando no consigue procesar la lectura con ninguno. El historial se almacena en CSV.

## Componentes

| Carpeta | Contenido |
|---|---|
| master/ | API, distribución, panel e historial |
| worker/ | Servicio de inferencia y lector del modelo JSON |
| training/ | Generación de datos, entrenamiento y evaluación |
| dataset/ | Lecturas sintéticas de entrenamiento |
| model/ | Árbol de decisión exportado |
| config/ | Configuración de Workers y perfiles de red |
| deployment/ | Servicios systemd y referencias de red |
| scripts/ | Scripts de inicio |
| evidencias/ | Resultados de las pruebas |
| docs/ | Informe y documentación complementaria |

## Modelo y evaluación

- Algoritmo: DecisionTreeClassifier.
- Entrenamiento: 400 lecturas; prueba: 100 lecturas.
- Exactitud de prueba: **94 %**, con 94 aciertos y 6 errores.
- Coincidencia entre scikit-learn y el modelo JSON: **100 de 100 predicciones evaluadas**.
- Dos lecturas críticas fueron clasificadas como Advertencia.

Los resultados corresponden a datos sintéticos; no representan una validación industrial.

## Rendimiento observado

Pruebas de 60 solicitudes con 4 clientes concurrentes:

| Métrica | Un Worker local | Dos Workers |
|---|---:|---:|
| Respuestas HTTP 200 | 60/60 | 60/60 |
| Resultados esperados | 60/60 | 60/60 |
| Registros guardados | 60/60 | 60/60 |
| Duración del lote | 2.146 s | 2.139 s |
| Respuestas exitosas/s | 27.96 | 28.05 |
| Latencia promedio | 140.04 ms | 139.11 ms |
| Percentil 95 | 330.713 ms | 334.259 ms |

Con dos Workers se distribuyeron 30 solicitudes a cada uno. Se realizó una ejecución por configuración: la diferencia observada no permite concluir una mejora de rendimiento.

## Validaciones realizadas

- Rechazo de campos faltantes y temperatura no numérica.
- Corrección y comprobación del rechazo de vibración negativa, NaN e infinito.
- HTTP 503 cuando ninguno de los Workers estaba disponible.
- Recuperación de respuestas HTTP 200 al restaurar los servicios.
- Servicios activos y clasificación correcta después de un reinicio.

La evidencia inicial de validación conserva el caso de vibración negativa aceptado antes de corregirlo.

## Consultar el sistema instalado

En edge-master:

```bash
systemctl is-active edge-master.service edge-worker.service
curl http://127.0.0.1:8000/api/status
```

Lectura de demostración:

```bash
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"temperatura_c":91,"vibracion_mm_s":9.8}'
```

Panel en la red de pruebas: http://192.168.0.17:8000

Los servicios de deployment/ corresponden a los equipos utilizados. Revise rutas, usuario y configuración de red antes de instalarlos en otros equipos.

## Documentación

- [Informe del proyecto](docs/Proyecto_Final_Profesional.docx)
- [Evaluador del modelo](training/evaluate_model.py)
- [Evidencias](evidencias/)

## Pendientes y límites

- Activar y comprobar la red Ethernet preparada.
- Demostrar el funcionamiento con Internet desconectado.
- Incorporar y probar el tercer nodo físico previsto.
- Verificar la restauración completa del respaldo.
- Ampliar las mediciones con ejecuciones repetidas.

La inferencia se ejecuta localmente y no utiliza una API de IA externa. El Master sigue siendo un punto único de fallo; el historial no está replicado.
