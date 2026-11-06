"""Fake del protocolo Qdrant para pruebas unitarias; no inicia almacenamiento local."""
from types import SimpleNamespace

from qdrant_client import models


class FakeQdrantClient:
    def __init__(self):
        self.collections = set()
        self.points = {}
        self.payload_indexes = set()

    def get_collections(self):
        return SimpleNamespace(collections=[SimpleNamespace(name=n) for n in self.collections])

    def create_collection(self, collection_name, vectors_config):
        self.collections.add(collection_name)

    def create_payload_index(self, collection_name, field_name, field_schema):
        self.payload_indexes.add((collection_name, field_name, field_schema))

    def upsert(self, collection_name, points, **kwargs):
        if collection_name not in self.collections:
            raise RuntimeError("collection missing")
        for point in points:
            self.points[str(point.id)] = SimpleNamespace(id=str(point.id), payload=dict(point.payload), vector=point.vector)

    @staticmethod
    def _matches(payload, query_filter):
        if query_filter is None:
            return True
        for condition in query_filter.must:
            value = payload.get(condition.key)
            expected = condition.match.value
            if value != expected:
                return False
        return True

    def scroll(self, collection_name, scroll_filter=None, limit=10, offset=None, **kwargs):
        rows = [
            point for point in self.points.values()
            if self._matches(point.payload, scroll_filter)
        ]
        start = int(offset or 0)
        page = rows[start:start + limit]
        next_offset = start + len(page) if start + len(page) < len(rows) else None
        return page, next_offset

    def query_points(self, collection_name, query_filter=None, limit=10, **kwargs):
        rows = [
            point for point in self.points.values()
            if self._matches(point.payload, query_filter)
        ]
        return SimpleNamespace(points=rows[:limit])

    def delete(self, collection_name, points_selector, **kwargs):
        if isinstance(points_selector, models.PointIdsList):
            ids = {str(item) for item in points_selector.points}
            for point_id in ids:
                self.points.pop(point_id, None)
            return
        if isinstance(points_selector, models.FilterSelector):
            ids = [
                point_id for point_id, point in self.points.items()
                if self._matches(point.payload, points_selector.filter)
            ]
            for point_id in ids:
                self.points.pop(point_id, None)

    def close(self):
        self.points.clear()
        self.collections.clear()
        self.payload_indexes.clear()
