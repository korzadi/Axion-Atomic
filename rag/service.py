import asyncio
import logging
import threading
import time
import uuid

from agent.secrets import find_secrets
from qdrant_client import QdrantClient, models
from api.config import settings
from api.ollama import embed
from rag.chunking import chunk_text

client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
logger = logging.getLogger(__name__)
_collection_lock = threading.Lock()
_collection_checked_at = 0.0
_COLLECTION_CHECK_INTERVAL_SECONDS = 60.0

MAX_MANUAL_INGEST_CHARS = 100_000
MAX_MANUAL_SOURCE_CHARS = 500


class SensitiveContentError(ValueError):
    """El contenido parece contener credenciales; nunca incluye el valor detectado."""


class KnowledgeStoreUnavailable(RuntimeError):
    """El almacén de conocimiento no pudo completar una operación."""


class EmbeddingServiceUnavailable(RuntimeError):
    """El servicio de embeddings no pudo procesar el contenido."""


def validate_manual_ingest(text: str, source: str, project_id: str) -> None:
    """Valida todo el material antes de invocar embeddings o persistencia."""
    _project_filter(project_id)
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_MANUAL_INGEST_CHARS:
        raise ValueError("El texto debe contener entre 1 y 100000 caracteres no vacíos")
    if not isinstance(source, str) or len(source) > MAX_MANUAL_SOURCE_CHARS:
        raise ValueError("El origen debe tener como máximo 500 caracteres")
    findings = find_secrets(text) + find_secrets(source)
    if findings:
        # No incluir el contenido ni el valor detectado en el mensaje o los logs.
        kinds = sorted({finding.kind for finding in findings})
        lines = sorted({finding.line for finding in findings})
        raise SensitiveContentError(
            "Contenido rechazado: se detectaron posibles credenciales "
            f"(tipos: {', '.join(kinds)}; líneas: {', '.join(map(str, lines))}). "
            "Elimina los valores sensibles antes de indexar."
        )


def ensure_collection():
    """Comprueba/crea la colección con caché breve y sincronización entre threads.

    Evita una petición get_collections a Qdrant en cada chat. Se vuelve a
    comprobar cada minuto para detectar cambios operativos y no marcar como
    inicializada una colección si Qdrant falla.
    """
    global _collection_checked_at
    now = time.monotonic()
    if now - _collection_checked_at < _COLLECTION_CHECK_INTERVAL_SECONDS:
        return
    with _collection_lock:
        now = time.monotonic()
        if now - _collection_checked_at < _COLLECTION_CHECK_INTERVAL_SECONDS:
            return
        existing = {x.name for x in client.get_collections().collections}
        if settings.qdrant_collection not in existing:
            client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=models.VectorParams(
                    size=settings.embed_dimension, distance=models.Distance.COSINE
                ),
            )
        _collection_checked_at = time.monotonic()


def _project_filter(project_id: str):
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("project_id es obligatorio")
    return models.Filter(
        must=[
            models.FieldCondition(
                key="project_id", match=models.MatchValue(value=project_id)
            )
        ]
    )


async def ingest_text(text, source, project_id: str, source_id: str | None = None):
    validate_manual_ingest(text, source, project_id)  # Antes de Qdrant y del embedder.
    try:
        source_id = str(uuid.UUID(source_id)) if source_id else str(uuid.uuid4())
    except (ValueError, TypeError, AttributeError):
        raise ValueError("source_id debe ser un UUID válido") from None
    try:
        await asyncio.to_thread(ensure_collection)
    except Exception:
        logger.error("RAG ingestion failed; knowledge store is unavailable")
        raise KnowledgeStoreUnavailable("El almacén de conocimiento no está disponible") from None
    points = []
    for index, chunk in enumerate(chunk_text(text)):
        try:
            vector = await embed(chunk)
        except Exception:
            logger.error("RAG ingestion failed; embedding service is unavailable")
            raise EmbeddingServiceUnavailable("El servicio de embeddings no está disponible") from None
        points.append(
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"text": chunk, "source": source, "source_id": source_id, "project_id": project_id, "chunk": index},
            )
        )
    if points:
        try:
            await asyncio.to_thread(client.upsert, collection_name=settings.qdrant_collection, points=points)
        except Exception:
            logger.exception("RAG ingestion failed while ensuring the Qdrant collection")
            raise KnowledgeStoreUnavailable("El almacén de conocimiento no está disponible") from None
    return len(points)


async def replace_source(source_id: str, text: str, source: str, project_id: str) -> int:
    """Reindexa una fuente conservando su ID; publica la nueva versión antes de retirar la anterior."""
    validate_manual_ingest(text, source, project_id)
    try:
        normalized_source_id = str(uuid.UUID(source_id))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("source_id debe ser un UUID válido") from None
    project_filter = models.Filter(
        must=_project_filter(project_id).must + [
            models.FieldCondition(key="source_id", match=models.MatchValue(value=normalized_source_id))
        ]
    )
    try:
        await asyncio.to_thread(ensure_collection)
        old_ids = []
        offset = None
        while True:
            points, next_offset = await asyncio.to_thread(
                client.scroll,
                collection_name=settings.qdrant_collection,
                scroll_filter=project_filter,
                limit=256,
                offset=offset,
                with_payload=["project_id", "source_id"],
                with_vectors=False,
            )
            old_ids.extend(point.id for point in points if (point.payload or {}).get("project_id") == project_id and (point.payload or {}).get("source_id") == normalized_source_id)
            if next_offset is None or not points:
                break
            offset = next_offset
            if len(old_ids) > 10000:
                raise KnowledgeStoreUnavailable("La fuente supera el límite seguro de reindexación")
        if not old_ids:
            raise ValueError("No se encontró la fuente en este proyecto")
    except ValueError:
        raise
    except KnowledgeStoreUnavailable:
        raise
    except Exception:
        logger.error("RAG source replacement failed while reading existing chunks")
        raise KnowledgeStoreUnavailable("El almacén de conocimiento no está disponible") from None

    new_points = []
    for index, chunk in enumerate(chunk_text(text)):
        try:
            vector = await embed(chunk)
        except Exception:
            logger.error("RAG source replacement failed; embedding service is unavailable")
            raise EmbeddingServiceUnavailable("El servicio de embeddings no está disponible") from None
        new_points.append(models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={"text": chunk, "source": source, "source_id": normalized_source_id, "project_id": project_id, "chunk": index},
        ))
    try:
        await asyncio.to_thread(
            client.upsert,
            collection_name=settings.qdrant_collection,
            points=new_points,
            wait=True,
        )
    except Exception:
        logger.error("RAG source replacement failed while publishing new chunks")
        raise KnowledgeStoreUnavailable("El almacén de conocimiento no está disponible") from None
    try:
        await asyncio.to_thread(
            client.delete,
            collection_name=settings.qdrant_collection,
            points_selector=models.PointIdsList(points=old_ids),
            wait=True,
        )
    except Exception:
        # La versión previa permanece intacta si no se logra limpiar; se intenta
        # retirar la nueva para evitar duplicados visibles.
        try:
            await asyncio.to_thread(
                client.delete,
                collection_name=settings.qdrant_collection,
                points_selector=models.PointIdsList(points=[point.id for point in new_points]),
                wait=True,
            )
        except Exception:
            logger.error("RAG source replacement rollback failed; manual reconciliation required")
        logger.error("RAG source replacement failed while retiring previous chunks")
        raise KnowledgeStoreUnavailable("No se pudo completar la sustitución de la fuente") from None
    return len(new_points)


async def delete_source(source_id: str, project_id: str) -> None:
    """Elimina todos los fragmentos de una fuente, siempre dentro del proyecto indicado."""
    project_filter = _project_filter(project_id)
    try:
        normalized_source_id = str(uuid.UUID(source_id))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("source_id debe ser un UUID válido") from None
    source_filter = models.Filter(
        must=project_filter.must + [
            models.FieldCondition(key="source_id", match=models.MatchValue(value=normalized_source_id))
        ]
    )
    try:
        await asyncio.to_thread(ensure_collection)
        await asyncio.to_thread(
            client.delete,
            collection_name=settings.qdrant_collection,
            points_selector=models.FilterSelector(filter=source_filter),
            wait=True,
        )
    except Exception:
        logger.error("RAG source deletion failed; knowledge store is unavailable")
        raise KnowledgeStoreUnavailable("El almacén de conocimiento no está disponible") from None


async def list_sources(project_id: str, limit: int = 100) -> dict:
    """Lista metadatos de fuentes sin devolver contenido ni vectores."""
    project_filter = _project_filter(project_id)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit debe estar entre 1 y 100")
    grouped = {}
    offset = None
    scanned = 0
    scan_cap = 5000
    try:
        await asyncio.to_thread(ensure_collection)
        while scanned < scan_cap and len(grouped) <= limit:
            page_size = min(256, scan_cap - scanned)
            points, next_offset = await asyncio.to_thread(
                client.scroll,
                collection_name=settings.qdrant_collection,
                scroll_filter=project_filter,
                limit=page_size,
                offset=offset,
                with_payload=["project_id", "source_id", "source", "chunk"],
                with_vectors=False,
            )
            for point in points:
                payload = point.payload or {}
                if payload.get("project_id") != project_id:
                    continue
                raw_id = payload.get("source_id")
                source_id = str(raw_id) if raw_id else None
                # Los registros antiguos sin source_id se agrupan como legado
                # por nombre de origen y se identifican como no administrables.
                key = source_id or "legacy:" + str(payload.get("source", "unknown"))
                item = grouped.setdefault(key, {
                    "source_id": source_id,
                    "source": str(payload.get("source", "unknown"))[:MAX_MANUAL_SOURCE_CHARS],
                    "chunks": 0,
                    "legacy": source_id is None,
                })
                item["chunks"] += 1
            scanned += len(points)
            if next_offset is None or not points:
                offset = None
                break
            offset = next_offset
        truncated = offset is not None or len(grouped) > limit
    except Exception:
        logger.error("RAG source listing failed; knowledge store is unavailable")
        raise KnowledgeStoreUnavailable("El almacén de conocimiento no está disponible") from None
    sources = sorted(
        grouped.values(),
        key=lambda item: (item["source"].casefold(), item["source_id"] or ""),
    )[:limit]
    return {"sources": sources, "truncated": truncated}


async def retrieve(query: str, project_id: str, limit: int = 5):
    project_filter = _project_filter(project_id)
    if not isinstance(query, str):
        raise ValueError("La consulta debe ser texto")
    if len(query) > 12_000:
        raise ValueError("La consulta supera el límite de 12000 caracteres")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("El límite de recuperación debe estar entre 1 y 20")
    if not query.strip():
        return ""
    try:
        await asyncio.to_thread(ensure_collection)
        vector = await embed(query)
        result = await asyncio.to_thread(
            client.query_points,
            collection_name=settings.qdrant_collection,
            query=vector,
            query_filter=project_filter,
            limit=limit,
            with_payload=True,
        )
        return "\\n\\n".join(
            "[Source: " + str(h.payload.get("source", "unknown")) + "]\\n"
            + str(h.payload.get("text", ""))
            for h in result.points
            if h.payload and h.payload.get("project_id") == project_id
        )
    except Exception:
        # No convertir una caída del almacén en una respuesta aparentemente válida sin contexto.
        logger.error("RAG retrieval failed; knowledge store is unavailable")
        raise KnowledgeStoreUnavailable("El almacén de conocimiento no está disponible") from None
