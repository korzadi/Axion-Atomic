---
name: implementation-planning
description: Convierte requisitos multiarchivo o complejos en un plan ejecutable, con archivos, dependencias, pruebas, riesgos y puntos de verificación.
---
# Planificación de implementación

Antes de modificar:
- Resume objetivo, alcance incluido y excluido.
- Identifica los archivos y símbolos concretos tras inspeccionar el repositorio.
- Ordena tareas por dependencia; divide en pasos pequeños y reversibles.
- Para cada paso especifica cambio esperado, prueba que lo demuestra y criterio de salida.
- Incluye contratos API, modelos, migraciones, permisos, frontend, documentación y observabilidad cuando apliquen.
- Marca riesgos, supuestos, bloqueos y decisiones que requieren autorización.
- Considera compatibilidad hacia atrás y despliegue, pero no despliegues.
- Guarda planes sustanciales en `docs/plans/` solo si el proyecto ya usa esa ubicación; de lo contrario usa la ubicación documentada del repo.
No inventes nombres de archivos ni detalles: primero inspecciona. No conviertas un plan en autorización para operaciones restringidas.
