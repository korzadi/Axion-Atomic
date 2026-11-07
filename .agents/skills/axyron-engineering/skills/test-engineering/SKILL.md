---
name: test-engineering
description: Diseña pruebas unitarias, integración, contratos, regresión y extremo a extremo para demostrar el comportamiento real.
---
# Ingeniería de pruebas

- Identifica framework, fixtures, convenciones y suite existente antes de crear tests.
- Escribe pruebas para comportamiento observable, no para detalles internos frágiles.
- Para bugs, reproduce primero el fallo con una prueba que falle por la causa correcta.
- Para cambios, cubre éxito, entradas inválidas, permisos, límites, errores, concurrencia e idempotencia según riesgo.
- Usa datos sintéticos aislados; nunca conectes pruebas a producción ni uses datos personales reales.
- Evita mocks que sustituyan precisamente la integración que se pretende verificar; usa tests de contrato o integración cuando sea viable.
- No marques tests como omitidos para ocultar fallos; explica cualquier skip.
- Ejecuta primero el test específico y luego la suite relevante.
- Informa comandos, exit code, cantidad de aprobadas/fallidas/omitidas y limitaciones.
- No afirmes que se ejecutó una prueba si solo la leíste o la añadiste.
