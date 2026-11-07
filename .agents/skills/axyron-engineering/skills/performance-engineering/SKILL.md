---
name: performance-engineering
description: Diagnostica y mejora rendimiento de backend, frontend, consultas, memoria y concurrencia con mediciones reproducibles.
---
# Ingeniería de rendimiento

- Mide antes de optimizar y define objetivo (latencia, throughput, memoria, CPU, tamaño o coste).
- Localiza cuello de botella con perfiles, métricas, logs o planes de consulta.
- Distingue latencia de red, CPU, I/O, locks, serialización y renderizado.
- Optimiza la causa dominante con el cambio mínimo.
- Considera caché, paginación, batching, índices, streaming y límites solo cuando el patrón lo justifique.
- Evita cachés sin invalidación, consultas N+1, loops bloqueantes y cargas completas innecesarias.
- Verifica que la mejora no rompe consistencia, aislamiento, seguridad ni experiencia de usuario.
- Compara antes/después con misma carga y entorno; informa metodología y variabilidad.
- No hagas pruebas de carga contra producción ni consumas recursos externos sin autorización.
