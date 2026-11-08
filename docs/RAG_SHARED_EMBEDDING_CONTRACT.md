# Contrato común de vectores e identidad de embeddings

## Hallazgo ARC-01

Los dos pipelines RAG consumen Ollama por transportes distintos: el indexador de repositorios usa `OllamaEmbedder` sobre `/api/embed`, mientras Studio usa `api.ollama.embed` sobre `/api/embeddings`.

Compartir la validación numérica no garantizaba que ambos transportes hubieran solicitado el mismo modelo o que un runtime devolviera el modelo esperado. Tampoco había un objeto común para comparar la identidad lógica de un espacio vectorial.

## Contrato de vectores

`rag/vector_contract.py`:

- exige dimensión positiva y exacta;
- valida cardinalidad de lotes;
- acepta únicamente componentes numéricos reales, excluyendo booleanos;
- rechaza valores no finitos (`NaN`, `+Inf`, `-Inf`);
- normaliza componentes a `float`.

`OllamaEmbedder` y el adaptador de Studio aplican el contrato antes de entregar, guardar o devolver vectores.

## Identidad del espacio vectorial

Se añade `rag/embedding_identity.py`:

- normaliza el alias Ollama sin etiqueta a la forma canónica `:latest`;
- conserva tags explícitos distintos como identidades diferentes;
- valida nombre de modelo y dimensión positiva;
- ofrece `EmbeddingIdentity.compatible_with` y `require_compatible_embeddings`, que fallan de forma cerrada ante modelo o dimensión incompatibles.

El indexador de repositorios expone la identidad configurada en `OllamaEmbedder.identity`. Studio construye la misma identidad a partir de `EMBED_MODEL` y `EMBED_DIMENSION`; sus claves de RCache usan el nombre canónico y la dimensión, evitando duplicar o confundir aliases.

Cuando la respuesta de `/api/embed` o `/api/embeddings` incluye un campo `model`, el transporte/adaptador comprueba que coincide con el modelo solicitado. Una discrepancia se rechaza antes de entregar o cachear el vector. Si el servidor no incluye ese campo, la comprobación de identidad de runtime no es posible en esa respuesta y se conserva la validación de dimensión/tipo/finitez.

## Regresión

- `tests/test_rag_vector_contract.py`: dimensión, cardinalidad, tipos, valores no finitos y normalización.
- `tests/test_api_embedding_contract.py`: vectores/caché inválidos, rechazo de modelo remoto distinto y clave canónica.
- `tests/test_rag_embedding_identity.py`: alias, tags, dimensiones, compatibilidad y respuesta del transporte de repositorios.
- `tests/test_rag_store_http.py`: regresiones HTTP del indexador y Qdrant.

## Compatibilidad y límites

No se cambia el modelo configurado, dimensión, endpoint, colección, contenido persistido ni estrategia de chunking. Los vectores históricos de Qdrant no se reescriben y no se elimina ni recrea ninguna colección.

La identidad común permite comparar configuraciones y cada pipeline valida el modelo que solicita. Sin embargo, `RepoIndexer` sigue siendo una clase construida externamente y no está conectada al runtime HTTP de Studio; no se afirma que hoy exista una única fábrica de configuración que fuerce la paridad de ambas instancias. Antes de compartir una colección en producción, el punto de composición debe invocar `require_compatible_embeddings` con las dos identidades efectivas. Además, si Ollama omite el modelo en su respuesta, el cliente no puede demostrar qué artefacto respondió únicamente con ese payload.

No se migran datos ni se cambia el contrato de payload para evitar mezclar silenciosamente puntos históricos con una identidad que no esté registrada en ellos.
