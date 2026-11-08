# Contrato común de vectores de embeddings

## Hallazgo ARC-01

Los dos pipelines RAG consumen Ollama por transportes distintos: el indexador de repositorios usa `OllamaEmbedder` sobre `/api/embed`, mientras Studio usa `api.ollama.embed` sobre `/api/embeddings`. Ambos configuraban la dimensión, pero la validación no era equivalente: se comprobaba principalmente el tamaño del vector y la cardinalidad del lote dependía del transporte.

Un vector con `NaN`, infinito, booleanos o componentes no numéricos podía superar validaciones parciales y fallar más tarde al persistirse o consultarse.

## Corrección

Se añadió `rag/vector_contract.py` como contrato puro compartido:

- exige dimensión positiva;
- valida dimensión exacta;
- acepta únicamente componentes numéricos reales, excluyendo booleanos;
- rechaza valores no finitos (`NaN`, `+Inf`, `-Inf`);
- normaliza componentes a `float`;
- valida también la cantidad de vectores de cada lote.

`OllamaEmbedder` aplica el contrato a cada lote antes de entregarlo al indexador. El adaptador de Studio aplica el mismo contrato a respuestas remotas y a valores recuperados de caché, antes de guardar o devolver el vector.

## Regresión

- `tests/test_rag_vector_contract.py`: dimensión, cardinalidad, tipos, valores no finitos y normalización.
- `tests/test_api_embedding_contract.py`: impide cachear una respuesta remota inválida y rechaza una entrada de caché inválida.
- `tests/test_rag_store_http.py`: conserva las pruebas HTTP de dimensión y lotes del indexador.

## Compatibilidad y límites

No se cambia el modelo configurado, dimensión, endpoint, colección, contenido persistido ni estrategia de chunking. Los vectores históricos de Qdrant no se reescriben. La validación se aplica en el límite de generación/lectura de caché para impedir que vectores malformados nuevos o cacheados lleguen a los consumidores.

Esta tarea fortalece el contrato de vectores, pero no conecta todavía `RepoIndexer` con las rutas HTTP de Studio ni unifica sus estrategias de chunking y recuperación.
