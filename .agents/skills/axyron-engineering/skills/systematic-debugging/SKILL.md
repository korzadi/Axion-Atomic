---
name: systematic-debugging
description: Investiga bugs, fallos de tests, errores de integración y comportamientos inesperados hasta encontrar su causa raíz antes de corregir.
---
# Depuración sistemática

Regla central: no apliques una corrección hasta tener evidencia de la causa raíz.

1. Reproduce el problema con los pasos, entorno y entrada más pequeños posibles.
2. Recoge logs y trazas relevantes, ocultando secretos y datos personales.
3. Compara comportamiento esperado y real; localiza la primera capa donde divergen.
4. Formula hipótesis concretas y prueba una por vez.
5. Sigue el flujo de datos entre frontend, API, dominio, persistencia y servicios externos.
6. Distingue causa raíz, factores contribuyentes y síntomas.
7. Escribe una prueba de regresión que reproduzca el defecto.
8. Aplica el cambio mínimo que resuelve la causa; evita reescrituras especulativas.
9. Ejecuta la prueba de regresión y las pruebas relacionadas.
10. Documenta causa, corrección, evidencia y riesgos residuales.
No ocultes fallos, no aumentes timeouts para esconder carreras, no desactives validaciones ni seguridad como solución.
