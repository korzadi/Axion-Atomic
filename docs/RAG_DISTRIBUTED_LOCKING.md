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
- En `rag.service`, SQLite y otros dialectos distintos de PostgreSQL usan un `asyncio.Lock` local por proyecto para desarrollo/CI. Este fallback no coordina procesos ni es válido como sustituto de PostgreSQL en producción. `SqlAlchemyMetaStore.project_lock` conserva su contrato específico de PostgreSQL.

## Cobertura

`RepoIndexer.index_project`, `reconcile_project` y `remove_project` usan el mismo guard. La reconciliación interna invocada desde la indexación no vuelve a adquirir el lock, evitando deadlock por adquisición recursiva.

Las mutaciones HTTP de `rag.service` (`ingest_text`, `replace_source` y `delete_source`) utilizan ahora `SqlAlchemyMetaStore(engine).project_lock` con el mismo identificador y la misma función de derivación de clave. La validación de contenido sensible, proyecto y límites ocurre antes de adquirir el lock. El bloqueo cubre la generación de embeddings y las escrituras/retiradas en Qdrant, evitando que el indexador de repositorio y la ingesta manual modifiquen simultáneamente el mismo proyecto.

Las pruebas del adaptador comprueban el SQL de adquisición/liberación, invalidación ante fallo de unlock y serialización entre dos instancias independientes del MetaStore con sesiones simuladas. Las pruebas de servicio verifican que ingestión, sustitución y eliminación mantienen el mismo lock, y que el rechazo de contenido sensible ocurre antes de reservar una conexión.

## Límites y despliegue

- El backend PostgreSQL debe permitir advisory locks (funcionalidad estándar de PostgreSQL).
- Cada operación bloqueada consume una conexión del pool durante el trabajo de embeddings/Qdrant; dimensionar el pool y el timeout de adquisición de acuerdo con la carga.
- El lock coordina únicamente código que use este guard y la misma convención de clave. No bloquea escritores externos que omitan el mecanismo.
- El servicio HTTP `rag.service` sigue siendo un pipeline de chunks/embeddings separado de `RepoIndexer`; ahora comparte su bloqueo por proyecto, pero no unifica su formato de datos ni su estrategia de recuperación.
- No se cambia configuración, base de datos, Qdrant ni VPS. La integración y el comportamiento en PostgreSQL real quedan sujetos a CI y revisión antes de despliegue.
