# Reconciliación RAG: concurrencia por proyecto

## Riesgo corregido

La reconciliación podía invocarse directamente mientras otra operación del mismo proyecto estaba indexando o eliminando datos. Aunque la indexación y la eliminación de proyectos ya compartían un asyncio.Lock, la entrada pública de reconciliación no adquiría ese bloqueo.

Una reconciliación concurrente podía comparar el conjunto SQL antes de que una sustitución de archivo confirmara sus nuevos IDs y borrar vectores que estaban en proceso de publicación.

## Cambio

- reconcile_project(project_id) adquiere el mismo lock por proyecto que index_project y remove_project.
- _reconcile_project(project_id) contiene la operación sin adquirir el lock; solo se usa desde rutas internas que ya poseen el bloqueo.
- La indexación llama al método interno para evitar una adquisición recursiva del mismo lock.
- Proyectos distintos conservan locks independientes.

## Regresiones

tests/test_rag_reconciliation_concurrency.py comprueba:
- La reconciliación pública espera mientras el proyecto está bloqueado.
- La reconciliación interna puede ejecutarse con el lock ya adquirido.
- El bloqueo de un proyecto no impide reconciliar otro proyecto.

## Límites

El lock es local a una instancia de RepoIndexer; no sustituye un bloqueo distribuido si varias instancias de API comparten la misma base de datos y colección Qdrant. La coordinación distribuida queda como requisito separado antes de ejecutar múltiples workers concurrentes sobre los mismos proyectos.