"""ARC-04 — Validación E2E contra un servidor Qdrant REAL y efímero.

Estas pruebas no usan FakeQdrantClient ni ningún doble del almacén vectorial:
solo se sustituye el cliente por uno apuntando al Qdrant desechable levantado
en CI (servicio `qdrant` del job `qdrant-e2e`) o, localmente, por la variable
`QDRANT_E2E_URL`. Las embeddings son vectores sintéticos deterministas
(funciones hash); Qdrant, sus filtros, índices, scroll, upsert y delete son
reales.

Política fail-closed: si `QDRANT_E2E_URL` está definida y Qdrant no responde,
LAS PRUEBAS FALLAN claramente; nunca degradan a dobles ni a resultados simulados.
Sin `QDRANT_E2E_URL` el módulo se omite de forma explícita (no hay evidencia
E2E en ese caso).

Cada prueba crea su propia colección con nombre único y la elimina al terminar.
La limpieza se limita estrictamente a esa colección; jamás a colecciones ajenas.
"""
import hashlib
import math
import os
import re
import unittest
import uuid
from unittest.mock import patch

from qdrant_client import QdrantClient, models

from rag import service
from rag.service import EmbeddingIdentityMigrationRequired

QDRANT_URL = os.environ.get("QDRANT_E2E_URL", "").strip()
QDRANT_API_KEY = os.environ.get("QDRANT_E2E_API_KEY", "").strip() or None
ACTIVE_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text").strip() or "nomic-embed-text"


def _token_vector(text: str, dimension: int) -> list[float]:
    """Embedding sintético determinista: bolsa de tokens ponderada por hash."""
    vector = [0.0] * dimension
    for token in re.findall(r"[a-záéíóúñ0-9]+", text.lower()):
        digest = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        vector[digest % dimension] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


async def _synthetic_embed(text: str):
    return _token_vector(text, service.settings.embed_dimension)


@unittest.skipUnless(QDRANT_URL, "QDRANT_E2E_URL no definida; sin evidencia E2E contra Qdrant real")
class RealQdrantE2ETests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30, check_compatibility=False)
        try:
            cls.client.get_collections()
        except Exception as exc:
            raise AssertionError(
                f"Qdrant real no disponible en {QDRANT_URL}: {exc}. "
                "La ejecución E2E no puede continuar ni degradar a dobles."
            ) from exc

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    async def asyncSetUp(self):
        self.collection = f"axion_e2e_{uuid.uuid4().hex}"
        self.client_ref = service.client
        self.collection_ref = service.settings.qdrant_collection
        self.checked_ref = service._collection_checked_at
        self.model_ref = service.settings.embed_model
        service.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30, check_compatibility=False)
        service.settings.qdrant_collection = self.collection
        service.settings.embed_model = ACTIVE_MODEL
        service._collection_checked_at = -service._COLLECTION_CHECK_INTERVAL_SECONDS
        self.embed_patch = patch.object(service, "embed", new=_synthetic_embed)
        self.embed_patch.start()

    async def asyncTearDown(self):
        self.embed_patch.stop()
        service.client.close()
        service.client = self.client_ref
        service.settings.qdrant_collection = self.collection_ref
        service.settings.embed_model = self.model_ref
        service._collection_checked_at = self.checked_ref
        self.client.delete_collection(collection_name=self.collection)

    async def _scroll_all(self, scroll_filter=None):
        points = []
        offset = None
        while True:
            batch, next_offset = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=scroll_filter,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points.extend(batch)
            if next_offset is None or not batch:
                return points
            offset = next_offset

    @staticmethod
    def _project_filter(project_id):
        return models.Filter(must=[
            models.FieldCondition(key="project_id", match=models.MatchValue(value=project_id))
        ])

    @staticmethod
    def _source_filter(project_id, source_id):
        return models.Filter(must=[
            models.FieldCondition(key="project_id", match=models.MatchValue(value=project_id)),
            models.FieldCondition(key="source_id", match=models.MatchValue(value=source_id)),
        ])

    async def test_ingest_indexes_real_points_with_full_payload(self):
        source_id = str(uuid.uuid4())
        chunks = await service.ingest_text(
            "Documentación sintética del proyecto alfa para validación E2E.",
            "manual-alfa", "project-alfa", source_id=source_id,
        )
        self.assertEqual(chunks, 1)
        points = await self._scroll_all(self._source_filter("project-alfa", source_id))
        self.assertEqual(len(points), 1)
        payload = points[0].payload
        self.assertEqual(payload["project_id"], "project-alfa")
        self.assertEqual(payload["source_id"], source_id)
        identity = service.EmbeddingIdentity.from_settings(service.settings)
        self.assertEqual(payload["embedding_model"], identity.model)
        self.assertEqual(payload["embedding_dimension"], identity.dimension)
        self.assertIn("Documentación sintética", payload["text"])
        listed = await service.list_sources("project-alfa")
        self.assertEqual([s["source_id"] for s in listed["sources"]], [source_id])
        self.assertEqual((await service.list_sources("project-beta"))["sources"], [])

    async def test_retrieval_requires_active_identity_and_blocks_cross_model_mixing(self):
        source_id = str(uuid.uuid4())
        await service.ingest_text(
            "Contenido privado exclusivo del proyecto delta con identidad alfa.",
            "manual-delta", "project-delta", source_id=source_id,
        )
        context = await service.retrieve("contenido privado exclusivo", "project-delta")
        self.assertIn("Contenido privado exclusivo", context)

        service.settings.embed_model = "otro-modelo-mismo-dimension"
        context_other = await service.retrieve("contenido privado exclusivo", "project-delta")
        self.assertNotIn("Contenido privado exclusivo", context_other)
        self.assertEqual(context_other.strip(), "")
        points = await self._scroll_all(self._project_filter("project-delta"))
        self.assertEqual(len(points), 1)
        service.settings.embed_model = ACTIVE_MODEL
        self.assertIn("Contenido privado exclusivo", await service.retrieve("contenido privado exclusivo", "project-delta"))

    async def test_replace_retires_all_prior_chunks_across_embedding_identities(self):
        source_id = str(uuid.uuid4())
        await service.ingest_text(
            "Versión original de la fuente épsilon.", "manual-épsilon", "project-épsilon", source_id=source_id,
        )
        service.settings.embed_model = "otro-modelo-mismo-dimension"
        replaced = await service.replace_source(
            source_id, "Versión actualizada de la fuente épsilon tras cambio de modelo.",
            "manual-épsilon-v2", "project-épsilon",
        )
        self.assertEqual(replaced, 1)
        points = await self._scroll_all(self._source_filter("project-épsilon", source_id))
        self.assertEqual(len(points), 1)
        self.assertIn("Versión actualizada", points[0].payload["text"])
        identity = service.EmbeddingIdentity.from_settings(service.settings)
        self.assertEqual(points[0].payload["embedding_model"], identity.model)
        listed = await service.list_sources("project-épsilon")
        self.assertEqual(listed["sources"][0]["source"], "manual-épsilon-v2")
        self.assertEqual(listed["sources"][0]["chunks"], 1)

    async def test_delete_source_removes_only_target_source_and_project(self):
        keep_id = str(uuid.uuid4())
        drop_id = str(uuid.uuid4())
        await service.ingest_text(
            "Fuente que debe permanecer en épsilon uno.", "manual-keep", "project-epsilon-1", source_id=keep_id,
        )
        await service.ingest_text(
            "Fuente que debe eliminarse de épsilon uno.", "manual-drop", "project-epsilon-1", source_id=drop_id,
        )
        await service.delete_source(drop_id, "project-epsilon-1")
        remaining = await self._scroll_all(self._project_filter("project-epsilon-1"))
        self.assertEqual([point.payload["source_id"] for point in remaining], [keep_id])

    async def test_same_source_id_in_two_projects_stays_isolated(self):
        source_id = str(uuid.uuid4())
        await service.ingest_text("Fuente compartida alfa en proyecto uno.", "manual-shared", "project-shared-1", source_id=source_id)
        await service.ingest_text("Fuente compartida beta en proyecto dos.", "manual-shared", "project-shared-2", source_id=source_id)

        replaced = await service.replace_source(
            source_id, "Fuente compartida actualizada solo en proyecto uno.", "manual-shared-v2", "project-shared-1",
        )
        self.assertEqual(replaced, 1)
        points_one = await self._scroll_all(self._source_filter("project-shared-1", source_id))
        points_two = await self._scroll_all(self._source_filter("project-shared-2", source_id))
        self.assertEqual(len(points_one), 1)
        self.assertIn("actualizada solo en proyecto uno", points_one[0].payload["text"])
        self.assertEqual(len(points_two), 1)
        self.assertIn("proyecto dos", points_two[0].payload["text"])

        await service.delete_source(source_id, "project-shared-1")
        self.assertEqual(await self._scroll_all(self._source_filter("project-shared-1", source_id)), [])
        points_two = await self._scroll_all(self._source_filter("project-shared-2", source_id))
        self.assertEqual(len(points_two), 1)
        self.assertIn("proyecto dos", points_two[0].payload["text"])

    async def test_legacy_vectors_without_identity_block_retrieval_and_are_preserved(self):
        source_id = str(uuid.uuid4())
        await service.ingest_text(
            "Fuente moderna con identidad completa en zeta.", "manual-zeta", "project-zeta", source_id=str(uuid.uuid4()),
        )
        legacy_id = str(uuid.uuid4())
        self.client.upsert(
            collection_name=self.collection,
            wait=True,
            points=[models.PointStruct(
                id=legacy_id,
                vector=_token_vector("vector histórico sin identidad", service.settings.embed_dimension),
                payload={"project_id": "project-zeta", "source_id": source_id, "text": "vector histórico sin identidad",
                         "path": f"manual/{source_id}", "chunk": 0},
            )],
        )
        with self.assertRaises(EmbeddingIdentityMigrationRequired):
            await service.retrieve("vector histórico", "project-zeta")
        legacy_points, _ = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=self._source_filter("project-zeta", source_id),
            limit=10,
            with_payload=True,
            with_vectors=False,
        )
        self.assertEqual(len(legacy_points), 1)
        self.assertEqual(legacy_points[0].id, legacy_id)

    async def test_replace_with_embedding_failure_publishes_no_points(self):
        source_id = str(uuid.uuid4())
        await service.ingest_text(
            "Fuente theta para fallo de embeddings.", "manual-theta", "project-theta", source_id=source_id,
        )

        async def failing_embed(_text):
            raise RuntimeError("embeddings apagados por prueba")

        with patch.object(service, "embed", new=failing_embed):
            with self.assertRaises(service.EmbeddingServiceUnavailable):
                await service.replace_source(
                    source_id, "Nuevo contenido que nunca debe publicarse.", "manual-theta-v2", "project-theta",
                )
        points = await self._scroll_all(self._source_filter("project-theta", source_id))
        self.assertEqual(len(points), 1)
        self.assertIn("Fuente theta", points[0].payload["text"])

    async def test_replace_nonexistent_source_fails_before_publishing(self):
        with self.assertRaises(ValueError):
            await service.replace_source(str(uuid.uuid4()), "contenido", "manual-inexistente", "project-iota")
        self.assertEqual(await self._scroll_all(self._project_filter("project-iota")), [])

    async def test_delete_missing_source_is_idempotent_noop(self):
        await service.delete_source(str(uuid.uuid4()), "project-kappa")
        self.assertEqual(await self._scroll_all(self._project_filter("project-kappa")), [])


if __name__ == "__main__":
    unittest.main()
