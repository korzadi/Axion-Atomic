"""Indexador incremental de repositorios. Respeta .gitignore/.axionignore y archivos sensibles (vía Workspace),
NO indexa archivos que contengan secretos, y elimina referencias obsoletas (archivos borrados o ahora con secretos)."""
import asyncio
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent.git import GitManager
from agent.secrets import find_secrets
from agent.workspace import Workspace
from core.errors import AxionError
from rag.chunker import chunk_file
from rag.embedder import Embedder
from rag.meta import MetaStore
from rag.store import Point, VectorStore

NS = uuid.UUID("6f1c2d5e-3b7a-4a55-9d0e-2a3f6c9b1e11")
SKIP_EXT = {"png", "jpg", "jpeg", "gif", "webp", "ico", "pdf", "zip", "gz", "tar", "woff", "woff2", "ttf", "eot", "mp4", "mp3",
            "map", "lock", "csv", "svg", "bin", "so", "dll", "exe", "class", "jar", "sqlite", "db"}
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "go.sum"}
MAX_INDEX_BYTES = 500_000


@dataclass
class IndexReport:
    indexed: list[str] = field(default_factory=list)
    unchanged: int = 0
    removed: list[str] = field(default_factory=list)
    skipped_secrets: list[str] = field(default_factory=list)
    skipped_other: int = 0
    chunks: int = 0
    errors: list[str] = field(default_factory=list)
    truncated: bool = False
    orphaned_removed: int = 0


def embed_text(rel: str, symbol: str | None, text: str) -> str:
    return f"{rel}\n{symbol or ''}\n{text}"


class RepoIndexer:
    def __init__(self, embedder: Embedder, store: VectorStore, meta: MetaStore, max_files: int = 5000):
        self.embedder, self.store, self.meta, self.max_files = embedder, store, meta, max_files
        self._locks: dict[str, asyncio.Lock] = {}

    async def index_project(self, ws: Workspace) -> IndexReport:
        pid = ws.project_id
        lock = self._locks.setdefault(pid, asyncio.Lock())
        async with lock:
            return await self._index(ws)

    async def _index(self, ws: Workspace) -> IndexReport:
        pid, rep = ws.project_id, IndexReport()
        await self.store.ensure()
        existing = await asyncio.to_thread(self.meta.list_files, pid)
        files = list(ws.walk(self.max_files + 1))
        if len(files) > self.max_files:
            files, rep.truncated = files[: self.max_files], True
        revision = await asyncio.to_thread(GitManager(ws).head)
        seen: set[str] = set()
        for rel in files:
            name, ext = rel.rsplit("/", 1)[-1], rel.rsplit(".", 1)[-1].lower()
            path = ws.root / rel
            try:
                size = path.stat().st_size
                if name in SKIP_NAMES or ext in SKIP_EXT or size > MAX_INDEX_BYTES or size == 0:
                    rep.skipped_other += 1
                    continue
                raw = path.read_bytes()
                if b"\0" in raw[:8192]:
                    rep.skipped_other += 1
                    continue
                text = raw.decode("utf-8", "replace")
                if find_secrets(text):
                    rep.skipped_secrets.append(rel)      # nunca se indexa; si estaba indexado, se retira (abajo)
                    continue
                seen.add(rel)
                sha = hashlib.sha256(raw).hexdigest()
                if existing.get(rel) == sha:
                    rep.unchanged += 1
                    continue
                chunks = chunk_file(rel, text)
                if not chunks:
                    rep.skipped_other += 1
                    continue
                vectors = await self.embedder.embed([embed_text(rel, c.symbol, c.text) for c in chunks])   # primero embeber: si falla, no se toca nada
                ids = [str(uuid.uuid5(NS, f"{pid}|{rel}|{sha}|{c.idx}")) for c in chunks]
                # Conservar la versión anterior hasta que la nueva esté publicada
                # y sus metadatos hayan quedado confirmados en la transacción SQL.
                old_ids = await asyncio.to_thread(self.meta.list_file_chunk_ids, pid, rel)
                await self.store.upsert([Point(i, v, {"project_id": pid, "path": rel, "chunk_id": i, "sha256": sha})
                                         for i, v in zip(ids, vectors)])
                await asyncio.to_thread(self.meta.replace_file, pid, rel, sha, revision, size, list(zip(ids, chunks)),
                                        datetime.now(timezone.utc).isoformat())
                # Si la limpieza falla, los vectores anteriores quedan huérfanos
                # pero el Retriever los descarta porque ya no existen en MetaStore.
                await self.store.delete_ids(old_ids)
                rep.indexed.append(rel); rep.chunks += len(chunks)
            except (AxionError, OSError, ValueError) as exc:
                rep.errors.append(f"{rel}: {exc}")
                seen.add(rel)                             # un error transitorio no debe borrar lo ya indexado
        if not rep.truncated:                             # con recorrido incompleto no se borra nada
            for gone in set(existing) - seen:
                try:
                    old_ids = await asyncio.to_thread(self.meta.list_file_chunk_ids, pid, gone)
                    # SQL es la fuente canónica: quitar primero los metadatos.
                    # Si falla la limpieza vectorial, reconcile_project reintentará.
                    await asyncio.to_thread(self.meta.delete_file, pid, gone)
                    rep.removed.append(gone)
                    await self.store.delete_ids(old_ids)
                except (AxionError, OSError, ValueError) as exc:
                    rep.errors.append(f"{gone}: {exc}")
        try:
            rep.orphaned_removed = await self._reconcile_project(pid)
        except (AxionError, OSError, ValueError) as exc:
            rep.errors.append(f"reconciliación de vectores huérfanos: {exc}")
        return rep

    async def reconcile_project(self, project_id: str) -> int:
        """Serializa la reconciliación con indexación y eliminación del mismo proyecto."""
        if not project_id or not isinstance(project_id, str):
            raise ValueError("project_id es obligatorio")
        lock = self._locks.setdefault(project_id, asyncio.Lock())
        async with lock:
            return await self._reconcile_project(project_id)

    async def _reconcile_project(self, project_id: str) -> int:
        """Elimina solo vectores del proyecto que ya no tienen fragmento SQL vigente.

        Método interno: el llamador debe poseer el lock del proyecto.
        """
        if not project_id or not isinstance(project_id, str):
            raise ValueError("project_id es obligatorio")
        canonical_ids = await asyncio.to_thread(self.meta.list_project_chunk_ids, project_id)
        vector_ids = await self.store.list_project_ids(project_id)
        orphaned = sorted(vector_ids - canonical_ids)
        if orphaned:
            await self.store.delete_ids(orphaned)
        return len(orphaned)

    async def remove_project(self, project_id: str) -> None:
        if not project_id or not isinstance(project_id, str):
            raise ValueError("project_id es obligatorio")
        lock = self._locks.setdefault(project_id, asyncio.Lock())
        async with lock:
            # SQL es la fuente canónica: retirar primero la visibilidad del índice.
            # Si Qdrant falla, los vectores quedan huérfanos e invisibles al Retriever;
            # reconcile_project puede eliminarlos de forma segura más tarde.
            await asyncio.to_thread(self.meta.delete_project_index, project_id)
            await self.store.delete_project(project_id)
