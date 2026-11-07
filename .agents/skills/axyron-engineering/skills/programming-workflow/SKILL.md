---
name: programming-workflow
description: Flujo principal de ingeniería para cualquier cambio de software en AXYRON ATOMIC; coordina análisis, planificación, implementación, pruebas, revisión y documentación.
---
# Flujo de programación de AXYRON

Usa esta skill como punto de entrada para tareas de programación medianas o grandes. No cargues todas las skills en cada turno: consulta `list_skills` y lee solo las que correspondan al problema.

## Antes de tocar código
1. Lee `AGENTS.md` si existe, además del README y las instrucciones locales del módulo.
2. Lee `.agents/project-context/SUMMARY.md` si existe; úsalo como índice provisional y contrasta cada dato importante con el código actual.
3. Comprueba estado Git, archivos relacionados, contratos, rutas, modelos de datos y pruebas existentes.
4. Identifica qué está implementado, qué está simulado, qué está en roadmap y qué no está conectado.
5. Define el resultado observable y los criterios de aceptación. Para requisitos ambiguos que cambien producto, seguridad o datos, pregunta una sola aclaración concreta; no bloquees tareas cuyo alcance ya está claro.

## Selección de skills
- Requisito o funcionalidad nueva: `feature-design`, `implementation-planning`.
- Código Python/API: `python-backend`, `api-contracts`.
- Interfaz web: `frontend-web`.
- Persistencia: `postgresql-database`.
- Bug: `systematic-debugging`.
- Funcionalidad o corrección: `test-engineering`.
- Seguridad: `secure-coding`.
- Revisión: `code-review`.
- Rendimiento: `performance-engineering`.
- Cambios Git: `git-workflow`.
- Documentación: `technical-documentation`.

## Implementación
- Cambios pequeños, enfocados, coherentes con el estilo del proyecto.
- No hagas refactors no solicitados ni amplíes el alcance silenciosamente.
- Mantén contratos frontend/backend sincronizados; no crees endpoints ficticios ni datos demo para ocultar funciones ausentes.
- No elimines capacidades existentes sin autorización explícita.
- No ejecutes scripts de skills ni comandos que no estén expuestos por herramientas autorizadas.
- Las modificaciones se proponen y requieren aprobación según el mecanismo del agente. Nunca afirmes que un cambio se aplicó antes de recibir confirmación de aplicación.

## Límites operativos
No despliegues, reinicies servicios, construyas imágenes, ejecutes migraciones reales, modifiques VPS, secretos, autenticación, custodia, fondos, bases de datos o infraestructura compartida sin autorización explícita. No alteres KorzadiVPN ni sus dependencias. No imprimas ni guardes secretos. No uses el socket Docker privilegiado del host ni desactives controles de seguridad.

## Cierre obligatorio
1. Ejecuta las pruebas relevantes disponibles y registra comandos/resultados reales.
2. Revisa diff, regresiones, seguridad y coherencia de documentación.
3. Separa claramente: implementado, probado, no probado, pendiente y bloqueado.
4. Actualiza `.agents/project-context/` solo si el análisis o arquitectura cambió materialmente; nunca escribas secretos.
5. No declares completado algo que no hayas verificado.
