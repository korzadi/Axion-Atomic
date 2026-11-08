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

La búsqueda manual filtra simultáneamente por `project_id`, `embedding_model` y `embedding_dimension`. Por tanto, dos modelos distintos con la misma dimensión no comparten resultados. La sustitución y eliminación de fuentes se limitan a la propiedad `project_id` + `source_id`, no a la identidad de embeddings activa: así también retiran fragmentos históricos de modelos anteriores dentro del mismo proyecto, sin tocar otra fuente ni otro proyecto. La recuperación sigue filtrando por la identidad activa.

### Tratamiento de vectores históricos

No se infiere retroactivamente la identidad de puntos anteriores ni se reescribe, elimina o recrea ninguna colección. Antes de recuperar contexto, Studio recorre los puntos del proyecto y comprueba que todos declaren ambos campos. Si encuentra un punto sin identidad, o no puede verificar hasta 10.000 puntos, falla de forma cerrada con `EmbeddingIdentityMigrationRequired` en lugar de ocultar silenciosamente el contexto legacy mediante un filtro.

Esto preserva los datos históricos, pero significa que los proyectos que ya tenían puntos manuales sin identidad necesitan una migración explícita y revisada antes de volver a usar su RAG. La migración no forma parte de este cambio y no se ejecuta automáticamente. Los proyectos nuevos, y los proyectos sin puntos históricos, pueden usar la identidad persistente desde la primera escritura.

### Regresión añadida

`tests/test_workspace_knowledge_upload_rag_integration.py` comprueba:
- Dos modelos de igual dimensión se indexan con identidades distintas y la recuperación de B no devuelve los textos de A.
- Los puntos legacy sin identidad bloquean la recuperación de forma explícita, sin eliminarlos.
- La integración de carga, listado, recuperación y aislamiento por proyecto continúa cubierta.


## Corrección tras CI del 8 de noviembre de 2026

La primera ejecución del contrato persistente (run `42492628012`) detectó siete fallos de regresión, con 954 pruebas aprobadas y 10 omitidas. La causa fue principalmente que los dobles antiguos no simulaban el nuevo preflight de lectura de Qdrant ni esperaban los índices y filtros adicionales. También había dos errores en las nuevas pruebas de integración (uso asíncrono de una función síncrona y una aserción demasiado amplia sobre puntos de ambos modelos).

Se actualizaron los contratos de prueba para:
- Simular explícitamente el scroll de preflight cuando se prueba la búsqueda aislada, sin depender de un Qdrant remoto.
- Verificar los campos de identidad incluidos en filtros de borrado.
- Esperar los cuatro índices de payload, incluido el índice INTEGER de dimensión.
- Comprobar directamente la identidad del punto del modelo B y la conservación del fallo cerrado para puntos legacy.

No se ha relajado el control de identidad ni se ha cambiado el tratamiento fail-closed de datos históricos. La nueva CI de estos ajustes debe aprobar antes de considerar validada ARC-01.


## Resultado de CI y endurecimiento adicional

La segunda ejecución, correspondiente al HEAD `8486e6c` (run `42492795887`), terminó con los cinco jobs en `success`: Python tests, container image build, PostgreSQL migrations, Studio browser E2E y Qdrant Cloud integration.

Durante la revisión del preflight se detectó una condición adicional: Python considera `bool` como subclase de `int`, por lo que un payload con `embedding_dimension=true` podía superar una comprobación de tipo demasiado permisiva. El preflight ahora exige:
- `embedding_model` de tipo string y no vacío tras eliminar espacios.
- `embedding_dimension` entero positivo, excluyendo explícitamente booleanos.

Se añadieron regresiones para modelo vacío, dimensión booleana, cero y dimensión serializada como texto. Esta ampliación está publicada después del HEAD que obtuvo CI 5/5; su propia ejecución de CI sigue pendiente. No se ha cambiado el filtro de recuperación ni se ha inferido identidad para puntos históricos.


### Seguimiento de CI del endurecimiento

La ejecución `42492913533` del HEAD `8d5a5b6` finalizó con cuatro jobs aprobados y un fallo en Python: `961 passed, 10 skipped, 1 failed`. El fallo no fue de la validación de identidad: la nueva prueba insertaba puntos en el doble Qdrant antes de crear su colección de prueba. Se corrigió inicializando la colección antes de insertar los casos malformados (commit `17586d9`). La nueva ejecución para ese commit debe confirmar la corrección; no se atribuye aprobación anticipada.


### Limpieza de versiones históricas de una fuente

Al sustituir o eliminar una fuente manual, la consulta de limpieza usa conjuntamente `project_id` y `source_id`. No añade `embedding_model` ni `embedding_dimension` al filtro de propiedad, porque esos campos describen el espacio vectorial de recuperación, no quién es dueño de la fuente. Esto evita dejar fragmentos huérfanos de una identidad de embeddings anterior. La regresión de integración crea el mismo `source_id` en dos proyectos, elimina la fuente de uno y comprueba que la del otro permanece intacta.
