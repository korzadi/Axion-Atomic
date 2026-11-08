"""Almacén vectorial. La búsqueda EXIGE project_id: no existe forma de consultar sin filtro de proyecto.
QdrantStore usa la API REST documentada de Qdrant (colección única + filtro por payload project_id)."""
import asyncio
import math
from dataclasses import dataclass
from typing import Protocol

from core.errors import AxionError, TransportError
from core.http import request_json


class StoreConfigError(AxionError):
    code = "store_config_error"


@dataclass(frozen=True)
class Point:
    id: str
    vector: list[float]
    payload: dict      # debe incluir project_id y path


@dataclass(frozen=True)
class Hit:
    id: str
    score: float
    payload: dict


class VectorStore(Protocol):
    async def ensure(self) -> None: ...
    async def upsert(self, points: list[Point]) -> None: ...
    async def delete_path(self, project_id: str, path: str) -> None: ...
    async def delete_ids(self, ids: list[str]) -> None: ...
    async def list_project_ids(self, project_id: str) -> set[str]: ...
    async def delete_project(self, project_id: str) -> None: ...
    async def search(self, project_id: str, vector: list[float], limit: int) -> list[Hit]: ...


def _require(project_id: str) -> None:
    if not project_id or not isinstance(project_id, str):
        raise ValueError("project_id es obligatorio")


def _validate_point_payload(payload: dict) -> None:
    """Exige el mismo contrato de aislamiento y trazabilidad en todos los stores."""
    if not isinstance(payload, dict):
        raise ValueError("payload debe ser un objeto")
    project_id = payload.get("project_id")
    path = payload.get("path")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("payload.project_id debe ser una cadena no vacía")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("payload.path debe ser una cadena no vacía")


class InMemoryVectorStore:
    """Implementación real (fuerza bruta, coseno) para desarrollo y pruebas; no persiste."""

    def __init__(self):
        self.points: dict[str, Point] = {}

    async def ensure(self) -> None: ...

    async def upsert(self, points):
        # Validar el lote completo antes de mutar el almacén: un punto inválido
        # no debe dejar una ingesta parcial en memoria.
        for point in points:
            _validate_point_payload(point.payload)
        for point in points:
            self.points[point.id] = point

    async def delete_path(self, project_id, path):
        _require(project_id)
        self.points = {k: p for k, p in self.points.items() if not (p.payload["project_id"] == project_id and p.payload["path"] == path)}

    async def delete_ids(self, ids):
        wanted = set(ids)
        if not wanted:
            return
        self.points = {key: point for key, point in self.points.items() if key not in wanted}

    async def list_project_ids(self, project_id):
        _require(project_id)
        return {key for key, point in self.points.items() if point.payload.get("project_id") == project_id}

    async def delete_project(self, project_id):
        _require(project_id)
        self.points = {k: p for k, p in self.points.items() if p.payload["project_id"] != project_id}

    async def search(self, project_id, vector, limit):
        _require(project_id)
        nq = math.sqrt(sum(x * x for x in vector)) or 1.0
        hits = []
        for p in self.points.values():
            if p.payload["project_id"] != project_id:
                continue
            npv = math.sqrt(sum(x * x for x in p.vector)) or 1.0
            hits.append(Hit(p.id, sum(a * b for a, b in zip(vector, p.vector)) / (nq * npv), p.payload))
        return sorted(hits, key=lambda h: -h.score)[:limit]


class QdrantStore:
    def __init__(self, base_url: str, collection: str, dimension: int, api_key: str | None = None, timeout: float = 60.0):
        self.base, self.collection, self.dim, self.timeout = base_url.rstrip("/"), collection, dimension, timeout
        self.headers = {"api-key": api_key} if api_key else {}

    async def _req(self, method: str, path: str, payload=None) -> dict:
        return await asyncio.to_thread(request_json, method, f"{self.base}/collections/{self.collection}{path}",
                                       payload, self.headers, self.timeout)

    async def ensure(self) -> None:
        """Crea la colección si no existe. Si existe con otra dimensión, FALLA (nunca la recrea ni borra datos)."""
        try:
            info = await self._req("GET", "")
            size = info["result"]["config"]["params"]["vectors"]["size"]
            if size != self.dim:
                raise StoreConfigError(f"La colección {self.collection} tiene dimensión {size}, se esperaba {self.dim}")
        except TransportError as exc:
            if exc.status != 404:
                raise
            await self._req("PUT", "", {"vectors": {"size": self.dim, "distance": "Cosine"}})
        for field in ("project_id", "path"):
            await self._req("PUT", "/index", {"field_name": field, "field_schema": "keyword"})

    async def upsert(self, points):
        # La validación precede a cualquier petición para impedir que un lote
        # parcialmente inválido publique sus primeros fragmentos.
        for point in points:
            _validate_point_payload(point.payload)
        for i in range(0, len(points), 64):
            batch = points[i:i + 64]
            await self._req("PUT", "/points?wait=true", {"points": [{"id": p.id, "vector": p.vector, "payload": p.payload} for p in batch]})

    @staticmethod
    def _filter(project_id: str, path: str | None = None) -> dict:
        _require(project_id)
        must = [{"key": "project_id", "match": {"value": project_id}}]
        if path is not None:
            must.append({"key": "path", "match": {"value": path}})
        return {"must": must}

    async def delete_path(self, project_id, path):
        await self._req("POST", "/points/delete?wait=true", {"filter": self._filter(project_id, path)})

    async def delete_ids(self, ids):
        if not ids:
            return
        await self._req("POST", "/points/delete?wait=true", {"points": list(ids)})

    async def list_project_ids(self, project_id):
        flt = self._filter(project_id)
        ids = set()
        offset = None
        while True:
            body = {"filter": flt, "limit": 256, "with_payload": False, "with_vectors": False}
            if offset is not None:
                body["offset"] = offset
            data = await self._req("POST", "/points/scroll", body)
            result = data.get("result") or {}
            ids.update(str(point["id"]) for point in result.get("points", []))
            next_offset = result.get("next_page_offset")
            if next_offset is None or next_offset == offset:
                break
            offset = next_offset
        return ids

    async def delete_project(self, project_id):
        await self._req("POST", "/points/delete?wait=true", {"filter": self._filter(project_id)})

    async def search(self, project_id, vector, limit):
        data = await self._req("POST", "/points/search", {"vector": vector, "limit": limit, "with_payload": True,
                                                          "filter": self._filter(project_id)})
        return [Hit(str(r["id"]), float(r["score"]), r.get("payload") or {}) for r in data.get("result", [])]
