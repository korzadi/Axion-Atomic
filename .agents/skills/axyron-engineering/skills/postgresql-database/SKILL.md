---
name: postgresql-database
description: Trabaja con PostgreSQL, diseño de esquemas, consultas, índices y migraciones seguras sin pérdida de datos.
---
# Ingeniería de bases de datos PostgreSQL

- Inspecciona esquema, migraciones, ORM, transacciones, constraints e índices existentes.
- Diseña claves, relaciones, unicidad, nulabilidad y borrado según reglas de negocio.
- Usa consultas parametrizadas; nunca interpolación SQL con datos no confiables.
- Evalúa índices con consultas y planes reales; evita indexar todo indiscriminadamente.
- Define migraciones versionadas, reversibilidad cuando sea posible y compatibilidad entre versiones de aplicación.
- Para tablas grandes considera locks, backfill por lotes, tiempo de ejecución y despliegue gradual.
- No borres, reinicialices, recrees ni vacíes bases de datos o volúmenes.
- No ejecutes migraciones contra producción ni cambies datos reales sin autorización expresa.
- Protege aislamiento por usuario/proyecto y verifica autorización en las consultas.
- Prueba constraints, concurrencia, rollback y compatibilidad en base de pruebas aislada.
- No muestres cadenas de conexión ni valores de secretos.
