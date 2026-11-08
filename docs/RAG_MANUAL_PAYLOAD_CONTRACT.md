# Contrato de payload común para fuentes RAG manuales

## Hallazgo ARC-01

El pipeline de repositorios utiliza el contrato vectorial común `project_id` + `path`, validado por `InMemoryVectorStore` y `QdrantStore`. La ingestión manual de Studio guardaba `project_id` y `source_id`, pero no `path`. Esto impedía que los puntos manuales satisficieran el mismo contrato de payload y dificultaba su interoperabilidad con los stores compartidos.

## Corrección

La ingestión y sustitución manual ahora escriben `path=manual/{source_id}`, usando el UUID ya validado de la fuente. Se conservan `source`, `source_id`, `project_id` y `chunk`; no cambia el formato de recuperación ni la identificación de fuentes existente.

La ruta sintética es un identificador de origen vectorial, no una ruta del filesystem. El prefijo `manual/` evita confundir una fuente subida/manual con una ruta de archivo del repositorio.

## Regresión

`tests/test_rag_manual_path_contract.py` comprueba que una ingestión manual produce simultáneamente el `project_id`, `path` y `source_id` esperados.

## Alcance y límites

Este cambio alinea el contrato de payload; no unifica aún las estrategias de fragmentación, embedding ni recuperación. El indexador de repositorios mantiene sus metadatos canónicos SQL y su recuperación híbrida. Studio mantiene el flujo manual Qdrant existente. No se migra, elimina ni reescribe ningún punto histórico.
