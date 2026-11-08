# Bloqueo distribuido de mutaciones RAG por proyecto

## Objetivo

La exclusión basada únicamente en `asyncio.Lock` protege una instancia de `RepoIndexer`, pero no coordina procesos API distintos. Cuando el indexador recibe un `SqlAlchemyMetaStore`, ahora combina el lock local con un advisory lock de sesión PostgreSQL, compartido por todos los workers conectados a la misma base.

## Contrato

- El ámbito del lock es un proyecto; proyectos distintos no se bloquean entre sí.
- La clave es un entero firmado de 64 bits derivado de BLAKE2b sobre un prefijo de dominio y el identificador del proyecto. No se usa el hash aleatorio de Python.
- La adquisición usa `pg_try_advisory_lock` y espera hasta 30 segundos por defecto.
- La conexión PostgreSQL queda reservada del pool durante la sección crítica porque los advisory locks pertenecen a la sesión.
- La salida ejecuta `pg_advisory_unlock` antes de devolver la conexión al pool.
- Si el desbloqueo falla o informa que no liberó el lock, la conexión se invalida para evitar devolver al pool una sesión potencialmente bloqueada.
- Si el proceso o la sesión PostgreSQL desaparece, PostgreSQL libera el advisory lock asociado a esa sesión.
- El fallback para MetaStores sin capacidad `project_lock` conserva el comportamiento local anterior, útil para SQLite y pruebas unitarias.

## Cobertura

`RepoIndexer.index_project`, `reconcile_project` y `remove_project` usan el mismo guard. La reconciliación interna invocada desde la indexación no vuelve a adquirir el lock, evitando deadlock por adquisición recursiva.

Las pruebas del adaptador comprueban el SQL de adquisición/liberación, invalidación ante fallo de unlock y serialización entre dos instancias independientes del MetaStore con sesiones simuladas.

## Límites y despliegue

- El backend PostgreSQL debe permitir advisory locks (funcionalidad estándar de PostgreSQL).
- Cada operación bloqueada consume una conexión del pool durante el trabajo de embeddings/Qdrant; dimensionar el pool y el timeout de adquisición de acuerdo con la carga.
- El lock coordina únicamente código que use este guard y la misma convención de clave. No bloquea escritores externos que omitan el mecanismo.
- El servicio HTTP `rag.service` de ingesta manual es un flujo distinto y no usa `RepoIndexer`; este cambio no afirma serializar ese flujo.
- No se cambia configuración, base de datos, Qdrant ni VPS. La integración y el comportamiento en PostgreSQL real quedan sujetos a CI y revisión antes de despliegue.
