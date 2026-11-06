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
        client.create_payload_index(
            collection_name=collection,
            field_name="project_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
            wait=True,
        )
        project_a = f"ci-project-a-{uuid.uuid4()}"
        project_b = f"ci-project-b-{uuid.uuid4()}"
        vector_a = [1.0] + [0.0] * 767
        vector_b = [0.0, 1.0] + [0.0] * 766
        client.upsert(
            collection_name=collection,
            wait=True,
            points=[
                models.PointStruct(id=str(uuid.uuid4()), vector=vector_a,
                                   payload={"project_id": project_a, "path": "a.txt", "text": "AXION RAG cloud probe A"}),
                models.PointStruct(id=str(uuid.uuid4()), vector=vector_b,
                                   payload={"project_id": project_b, "path": "b.txt", "text": "AXION RAG cloud probe B"}),
            ],
        )

        result_a = client.query_points(
            collection_name=collection,
            query=vector_a,
            query_filter=models.Filter(must=[
                models.FieldCondition(key="project_id", match=models.MatchValue(value=project_a))
            ]),
            limit=5,
            with_payload=True,
        )
        if len(result_a.points) != 1 or result_a.points[0].payload.get("project_id") != project_a:
            raise RuntimeError("La búsqueda autenticada o el aislamiento por proyecto falló.")

        client.delete(
            collection_name=collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(must=[
                    models.FieldCondition(key="project_id", match=models.MatchValue(value=project_a))
                ])
            ),
            wait=True,
        )
        remaining_a = client.count(
            collection_name=collection,
            count_filter=models.Filter(must=[
                models.FieldCondition(key="project_id", match=models.MatchValue(value=project_a))
            ]),
            exact=True,
        ).count
        remaining_b = client.count(
            collection_name=collection,
            count_filter=models.Filter(must=[
                models.FieldCondition(key="project_id", match=models.MatchValue(value=project_b))
            ]),
            exact=True,
        ).count
        if remaining_a != 0 or remaining_b != 1:
            raise RuntimeError("La eliminación filtrada no respetó el aislamiento entre proyectos.")

        print("PASS: Qdrant Cloud autenticado; crear, insertar, buscar, aislar proyectos y borrar puntos.")
        return 0
    finally:
        if created:
            # La limpieza se limita estrictamente a la colección aleatoria creada por esta ejecución.
            client.delete_collection(collection_name=collection)
            print("LIMPIEZA: colección temporal propia eliminada.")
        client.close()


if __name__ == "__main__":
    sys.exit(main())
