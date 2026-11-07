---
name: code-review
description: Revisa cambios de código de forma independiente para detectar defectos, regresiones, riesgos de seguridad y desviaciones de requisitos antes de cerrar una tarea.
---
# Revisión de código

Revisa el diff contra requisitos y comportamiento existente. Prioriza hallazgos por severidad:
- Crítico: exposición de secretos/datos, ejecución no autorizada, pérdida de fondos/datos o bypass de seguridad.
- Alto: autorización rota, vulnerabilidad explotable, corrupción de datos, fallo amplio.
- Medio: bug funcional, regresión, manejo incorrecto de errores, concurrencia o rendimiento importante.
- Bajo: mantenibilidad, claridad o deuda técnica sin impacto inmediato.

Para cada hallazgo indica archivo/línea, escenario reproducible, impacto y corrección recomendada. Verifica:
1. Cumplimiento de requisitos y alcance.
2. Casos límite, errores y compatibilidad.
3. Validación, autorización, aislamiento y secretos.
4. Transacciones, idempotencia y concurrencia.
5. Contratos frontend/backend y accesibilidad.
6. Pruebas relevantes y cobertura de regresión.
7. Documentación y configuración.
No inventes hallazgos ni bloquees por preferencias estilísticas. Si no hay reviewer independiente disponible, realiza una auto-revisión explícita y declara esa limitación. No fusionar ni publicar sin autorización.
