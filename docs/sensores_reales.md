# Lecturas de sensores reales

El prototipo recibe lecturas de una ESP32 conectada por USB al edge-master.
La sonda DS18B20 mide temperatura en °C y el ADXL345 entrega aceleración
en los ejes X, Y y Z, expresada en m/s². El servicio edge-sensor lee las
líneas JSON y el Master presenta las lecturas recientes en /api/sensor y
en el panel. Una lectura se considera conectada cuando es reciente.

La aceleración mostrada incluye la gravedad. No equivale directamente a
velocidad de vibración en mm/s. El árbol de decisión existente fue entrenado
con datos sintéticos de temperatura y vibración en mm/s; por ello, las
lecturas del ADXL345 aún no alimentan sus clasificaciones. Esta etapa
demuestra adquisición e integración de sensores físicos, mientras que la
clasificación continúa como demostración académica con datos simulados.

La evidencia inicial de recepción USB está en
evidencias/sensores_reales_usb_20261014_065120_488260.jsonl.
