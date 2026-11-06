import uuid
from qdrant_client import QdrantClient, models
from api.config import settings
from api.ollama import embed
from rag.chunking import chunk_text

client = QdrantClient(url=settings.qdrant_url)


def ensure_collection():
    existing = {x.name for x in client.get_collections().collections}
    if settings.qdrant_collection not in existing:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=models.VectorParams(
                size=settings.embed_dimension, distance=models.Distance.COSINE
            ),
        )


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


async def ingest_text(text, source, project_id: str):
    _project_filter(project_id)  # Validar antes de acceder a Qdrant.
    ensure_collection()
    points = []
    for index, chunk in enumerate(chunk_text(text)):
        vector = await embed(chunk)
        points.append(
            models.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"text": chunk, "source": source, "project_id": project_id, "chunk": index},
            )
        )
    if points:
        client.upsert(collection_name=settings.qdrant_collection, points=points)
    return len(points)


async def retrieve(query: str, project_id: str, limit: int = 5):
    project_filter = _project_filter(project_id)
    if not query.strip():
        return ""
    try:
        ensure_collection()
        vector = await embed(query)
        hits = client.query_points(
            collection_name=settings.qdrant_collection,
            query=vector,
            query_filter=project_filter,
            limit=limit,
            with_payload=True,
        ).points
        return "\n\n".join(
            "[Source: " + str(h.payload.get("source", "unknown")) + "]\n"
            + str(h.payload.get("text", ""))
            for h in hits
            if h.payload and h.payload.get("project_id") == project_id
        )
    except Exception:
        return ""
