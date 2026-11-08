# Redacción defensiva de secretos en recuperación RAG heredada

## Hallazgo

La ingestión manual ahora rechaza patrones de credenciales detectables antes de generar embeddings o persistir nuevos puntos. Sin embargo, el almacén Qdrant puede contener documentos indexados antes de esa protección, y también puede recibir registros heredados o importados por otros mecanismos.

La recuperación manual alimenta contexto a las rutas de chat. Confiar exclusivamente en la validación de nuevas ingestiones dejaría los registros antiguos fuera de la protección.

## Corrección

`rag.service.retrieve` aplica ahora `agent.secrets.redact` tanto al texto recuperado como al nombre de origen antes de construir el contexto. El filtro exacto por `project_id` y la validación defensiva del payload se mantienen.

La redacción no altera el contenido almacenado en Qdrant; protege el contexto que se entrega al modelo. Los registros originales requieren una tarea separada de auditoría y saneamiento para su eliminación o reindexación, bajo autorización y con respaldo apropiado.

## Regresión

`tests/test_rag_manual_ingest.py` incorpora un caso que simula un punto legado con una clave AWS sintética en el cuerpo y una asignación de credencial en el campo de origen. Comprueba que:
- los valores originales no aparecen en el contexto devuelto;
- aparecen marcadores de redacción;
- el contenido no sensible se conserva;
- la consulta sigue filtrada por el proyecto solicitado.

## Límite

`agent.secrets.redact` es heurístico y no garantiza detectar todos los secretos. Esta medida es defensa adicional, no certificación de que el contenido histórico esté limpio. No se modifica ni elimina ningún dato persistido.
