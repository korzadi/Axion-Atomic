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

El indexador de repositorios expone la identidad configurada en `OllamaEmbedder.identity`. Studio y el indexador pueden construir la identidad desde el mismo objeto de configuración mediante `EmbeddingIdentity.from_settings(settings)` y `OllamaEmbedder.from_settings(transport, settings)`. La API usa el mismo constructor de identidad. Sus claves de RCache usan el nombre canónico y la dimensión, evitando duplicar o confundir aliases.

Cuando la respuesta de `/api/embed` o `/api/embeddings` incluye un campo `model`, el transporte/adaptador comprueba que coincide con el modelo solicitado. Una discrepancia se rechaza antes de entregar o cachear el vector. Si el servidor no incluye ese campo, la comprobación de identidad de runtime no es posible en esa respuesta y se conserva la validación de dimensión/tipo/finitez.

## Composición segura del indexador

`RepoIndexer` valida el contrato en su constructor, antes de indexar o escribir: si el almacén declara una dimensión, debe coincidir con la del embedder. `QdrantStore` e `InMemoryVectorStore` aceptan opcionalmente `embedding_identity`; cuando se declara, el indexador exige una identidad válida y exactamente compatible (modelo canónico + dimensión). La identidad sigue siendo opcional para no romper adaptadores y pruebas existentes que no declaran metadatos de modelo.

Esto hace efectiva la comprobación en el punto de composición del pipeline de repositorios. No equivale todavía a una fábrica única entre Studio y RepoIndexer: la ruta manual no construye `RepoIndexer` y debe recibir la misma identidad al crear su store compartido. No se presume paridad automática cuando no se declara identidad.

## Regresión

- `tests/test_rag_vector_contract.py`: dimensión, cardinalidad, tipos, valores no finitos y normalización.
- `tests/test_api_embedding_contract.py`: vectores/caché inválidos, rechazo de modelo remoto distinto y clave canónica.
- `tests/test_rag_embedding_identity.py`: alias, tags, dimensiones, compatibilidad y respuesta del transporte de repositorios.
- `tests/test_rag_embedding_composition.py`: validación de dimensión e identidad en el constructor de `RepoIndexer`, incluida la compatibilidad heredada de stores sin identidad declarada.
- `tests/test_rag_store_http.py`: regresiones HTTP del indexador y Qdrant.

## Compatibilidad y límites

No se cambia el modelo configurado, dimensión, endpoint, colección, contenido persistido ni estrategia de chunking. Los vectores históricos de Qdrant no se reescriben y no se elimina ni recrea ninguna colección.

La identidad común permite comparar configuraciones y cada pipeline valida el modelo que solicita. Sin embargo, `RepoIndexer` sigue siendo una clase construida externamente y no está conectada al runtime HTTP de Studio; no se afirma que hoy exista una única fábrica de configuración que fuerce la paridad de ambas instancias. Antes de compartir una colección en producción, el punto de composición debe invocar `require_compatible_embeddings` con las dos identidades efectivas. Además, si Ollama omite el modelo en su respuesta, el cliente no puede demostrar qué artefacto respondió únicamente con ese payload.

No se migran datos ni se cambia el contrato de payload para evitar mezclar silenciosamente puntos históricos con una identidad que no esté registrada en ellos.


## Identidad persistente en el RAG manual de Studio (ARC-01)

La ruta manual de Studio ahora escribe en cada punto dos campos de payload:
- `embedding_model`: nombre Ollama canónico (incluye `:latest` cuando el alias no declara tag).
- `embedding_dimension`: dimensión configurada del vector.

La búsqueda manual filtra simultáneamente por `project_id`, `embedding_model` y `embedding_dimension`. Por tanto, dos modelos distintos con la misma dimensión no comparten resultados. La sustitución y eliminación de fuentes también se limitan a la identidad activa, evitando borrar puntos de otra identidad por compartir `source_id`.

### Tratamiento de vectores históricos

No se infiere retroactivamente la identidad de puntos anteriores ni se reescribe, elimina o recrea ninguna colección. Antes de recuperar contexto, Studio recorre los puntos del proyecto y comprueba que todos declaren ambos campos. Si encuentra un punto sin identidad, o no puede verificar hasta 10.000 puntos, falla de forma cerrada con `EmbeddingIdentityMigrationRequired` en lugar de ocultar silenciosamente el contexto legacy mediante un filtro.

Esto preserva los datos históricos, pero significa que los proyectos que ya tenían puntos manuales sin identidad necesitan una migración explícita y revisada antes de volver a usar su RAG. La migración no forma parte de este cambio y no se ejecuta automáticamente. Los proyectos nuevos, y los proyectos sin puntos históricos, pueden usar la identidad persistente desde la primera escritura.

### Regresión añadida

`tests/test_workspace_knowledge_upload_rag_integration.py` comprueba:
- Dos modelos de igual dimensión se indexan con identidades distintas y la recuperación de B no devuelve los textos de A.
- Los puntos legacy sin identidad bloquean la recuperación de forma explícita, sin eliminarlos.
- La integración de carga, listado, recuperación y aislamiento por proyecto continúa cubierta.
