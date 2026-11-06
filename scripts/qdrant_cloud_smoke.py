"""Smoke test autenticado de Qdrant Cloud; usa y elimina solo una colección efímera propia."""
import os
import sys
import uuid
from urllib.parse import urlsplit

from qdrant_client import QdrantClient, models


def main() -> int:
    url = os.environ.get("QDRANT_URL", "").strip()
    api_key = os.environ.get("QDRANT_API_KEY", "").strip()
    if not url or not api_key:
        print("SKIP: faltan QDRANT_URL (Actions variable) o QDRANT_API_KEY (Actions secret).")
        return 0

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host.endswith(".qdrant.io") or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise SystemExit("ERROR: QDRANT_URL no es un endpoint HTTPS válido de Qdrant Cloud.")

    collection = f"axion_ci_{uuid.uuid4().hex}"
    client = QdrantClient(url=url, api_key=api_key, timeout=30, check_compatibility=False)
    created = False
    try:
        # Solo se crea un nombre aleatorio; nunca se consulta ni modifica la colección de producción.
        client.create_collection(
            collection_name=collection,
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE),
        )
        created = True
        for field_name in ("project_id", "source_id"):
            client.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )

        project_a = f"ci-project-a-{uuid.uuid4()}"
        project_b = f"ci-project-b-{uuid.uuid4()}"
        source_a = str(uuid.uuid4())
        source_b = str(uuid.uuid4())
        vector_a = [1.0] + [0.0] * 767
        vector_b = [0.0, 1.0] + [0.0] * 766
        old_a_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        project_b_id = str(uuid.uuid4())
        client.upsert(
            collection_name=collection,
            wait=True,
            points=[
                models.PointStruct(id=old_a_ids[0], vector=vector_a,
                    payload={"project_id": project_a, "source_id": source_a, "chunk": 0, "text": "AXION old source chunk 0"}),
                models.PointStruct(id=old_a_ids[1], vector=vector_a,
                    payload={"project_id": project_a, "source_id": source_a, "chunk": 1, "text": "AXION old source chunk 1"}),
                models.PointStruct(id=project_b_id, vector=vector_b,
                    payload={"project_id": project_b, "source_id": source_b, "chunk": 0, "text": "AXION isolated project B"}),
            ],
        )

        project_filter = models.Filter(must=[
            models.FieldCondition(key="project_id", match=models.MatchValue(value=project_a))
        ])
        source_filter = models.Filter(must=[
            models.FieldCondition(key="project_id", match=models.MatchValue(value=project_a)),
            models.FieldCondition(key="source_id", match=models.MatchValue(value=source_a)),
        ])
        result_a = client.query_points(
            collection_name=collection, query=vector_a,
            query_filter=project_filter, limit=5, with_payload=True,
        )
        if len(result_a.points) != 2 or any(p.payload.get("project_id") != project_a for p in result_a.points):
            raise RuntimeError("La búsqueda autenticada o el aislamiento por proyecto falló.")

        # Simula reindexación: publicar la versión nueva y retirar únicamente
        # los fragmentos anteriores de esa fuente dentro de ese mismo proyecto.
        replacement_id = str(uuid.uuid4())
        client.upsert(
            collection_name=collection, wait=True,
            points=[models.PointStruct(id=replacement_id, vector=vector_a,
                payload={"project_id": project_a, "source_id": source_a, "chunk": 0,
                         "text": "AXION replacement source version"})],
        )
        old_points, _ = client.scroll(
            collection_name=collection, scroll_filter=source_filter, limit=10,
            with_payload=["project_id", "source_id"], with_vectors=False,
        )
        old_ids = [p.id for p in old_points if p.id != replacement_id]
        if set(old_ids) != set(old_a_ids):
            raise RuntimeError("El listado de fragmentos de la fuente no coincide.")
        client.delete(
            collection_name=collection,
            points_selector=models.PointIdsList(points=old_ids), wait=True,
        )
        current, _ = client.scroll(
            collection_name=collection, scroll_filter=source_filter, limit=10,
            with_payload=True, with_vectors=False,
        )
        if len(current) != 1 or current[0].id != replacement_id or current[0].payload.get("text") != "AXION replacement source version":
            raise RuntimeError("La reindexación no conservó exactamente la versión nueva.")

        # Eliminación de fuente filtrada; el proyecto B debe permanecer intacto.
        client.delete(
            collection_name=collection,
            points_selector=models.FilterSelector(filter=source_filter),
            wait=True,
        )
        remaining_a = client.count(collection_name=collection, count_filter=project_filter, exact=True).count
        remaining_b = client.count(
            collection_name=collection,
            count_filter=models.Filter(must=[
                models.FieldCondition(key="project_id", match=models.MatchValue(value=project_b))
            ]), exact=True,
        ).count
        if remaining_a != 0 or remaining_b != 1:
            raise RuntimeError("La eliminación de fuente no respetó el aislamiento entre proyectos.")

        print("PASS: Qdrant Cloud autenticado; crear, indexar, insertar, buscar, aislar, reindexar y eliminar fuentes.")
        return 0
    finally:
        if created:
            # La limpieza se limita estrictamente a la colección aleatoria creada por esta ejecución.
            client.delete_collection(collection_name=collection)
            print("LIMPIEZA: colección temporal propia eliminada.")
        client.close()


if __name__ == "__main__":
    sys.exit(main())
