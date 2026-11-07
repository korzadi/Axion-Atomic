---
name: architecture-design
description: Analiza límites de módulos, dependencias, flujos de datos y decisiones arquitectónicas para cambios mantenibles y compatibles.
---
# Diseño de arquitectura

1. Mapea componentes, responsabilidades, dependencias y flujos reales.
2. Identifica límites de dominio, puntos de entrada y contratos entre capas.
3. Evita ciclos, duplicación de lógica y acoplamiento a infraestructura.
4. Prefiere patrones existentes y cambios incrementales antes que reescrituras.
5. Evalúa fallos parciales, disponibilidad, idempotencia, observabilidad y recuperación.
6. Considera multiusuario y multitenencia: cada acceso a datos debe respetar el ámbito autorizado.
7. Registra decisiones relevantes, alternativas y consecuencias en ADR cuando el repositorio tenga esa práctica.
8. No añadas microservicios, colas, caches o nuevas dependencias sin justificar necesidad.
9. Comprueba compatibilidad con infraestructura y despliegue actuales, sin ejecutar despliegues.
