"""Metadatos y texto de fragmentos + memorias de proyecto, sobre una conexión DB-API (PostgreSQL con psycopg
en producción, placeholder '%s'; SQLite en pruebas, placeholder '?'). SQL portable; transacciones explícitas.
Toda consulta filtra por project_id."""
import threading
from contextlib import contextmanager

from rag.chunker import Chunk

CHUNK_COLS = "id, path, idx, start_line, end_line, symbol, kind, text"


def _row(r) -> dict:
    return dict(zip(("id", "path", "idx", "start_line", "end_line", "symbol", "kind", "text"), r))


class MetaStore:
    def __init__(self, conn, placeholder: str = "?"):
        self.conn, self.ph, self.lock = conn, placeholder, threading.RLock()

    def _sql(self, s: str) -> str:
        return s if self.ph == "?" else s.replace("?", self.ph)

    @contextmanager
    def _tx(self):
        with self.lock:
            cur = self.conn.cursor()
            try:
                yield cur
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.close()

    def _q(self, sql: str, params=()) -> list:
        with self._tx() as cur:
            cur.execute(self._sql(sql), params)
            return cur.fetchall()

    def _x(self, sql: str, params=()) -> int:
        with self._tx() as cur:
            cur.execute(self._sql(sql), params)
            return cur.rowcount

    # API pública para otros módulos (aprobaciones, auditoría) que comparten la conexión
    def sql(self, s: str) -> str:
        return self._sql(s)

    def transaction(self):
        return self._tx()

    def query(self, sql: str, params=()) -> list:
        return self._q(sql, params)

    def execute(self, sql: str, params=()) -> int:
        return self._x(sql, params)

    # ---------- índice de archivos
    def list_files(self, project_id: str) -> dict[str, str]:
        return dict(self._q("SELECT path, sha256 FROM rag_files WHERE project_id = ?", (project_id,)))

    def list_file_chunk_ids(self, project_id: str, path: str) -> list[str]:
        """Devuelve los IDs vectoriales vigentes de un archivo dentro de su proyecto."""
        rows = self._q(
            "SELECT id FROM rag_chunks WHERE project_id = ? AND path = ? ORDER BY idx",
            (project_id, path),
        )
        return [row[0] for row in rows]

    def list_project_chunk_ids(self, project_id: str) -> set[str]:
        """Devuelve todos los IDs de fragmentos SQL vigentes de un proyecto."""
        rows = self._q("SELECT id FROM rag_chunks WHERE project_id = ?", (project_id,))
        return {row[0] for row in rows}

    def replace_file(self, project_id: str, path: str, sha: str, revision: str | None, size: int,
                     chunks: list[tuple[str, Chunk]], now_iso: str) -> None:
        with self._tx() as cur:
            cur.execute(self._sql("DELETE FROM rag_chunks WHERE project_id = ? AND path = ?"), (project_id, path))
            cur.execute(self._sql("DELETE FROM rag_files WHERE project_id = ? AND path = ?"), (project_id, path))
            cur.execute(self._sql("INSERT INTO rag_files (project_id, path, sha256, revision, size_bytes, chunk_count, indexed_at) "
                                  "VALUES (?, ?, ?, ?, ?, ?, ?)"), (project_id, path, sha, revision, size, len(chunks), now_iso))
            cur.executemany(self._sql("INSERT INTO rag_chunks (id, project_id, path, idx, start_line, end_line, symbol, kind, text) "
                                      "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"),
                            [(cid, project_id, path, c.idx, c.start_line, c.end_line, c.symbol, c.kind, c.text) for cid, c in chunks])

    def delete_file(self, project_id: str, path: str) -> None:
        with self._tx() as cur:
            cur.execute(self._sql("DELETE FROM rag_chunks WHERE project_id = ? AND path = ?"), (project_id, path))
            cur.execute(self._sql("DELETE FROM rag_files WHERE project_id = ? AND path = ?"), (project_id, path))

    def delete_project_index(self, project_id: str) -> None:
        with self._tx() as cur:
            cur.execute(self._sql("DELETE FROM rag_chunks WHERE project_id = ?"), (project_id,))
            cur.execute(self._sql("DELETE FROM rag_files WHERE project_id = ?"), (project_id,))

    def get_chunks(self, project_id: str, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self._q(f"SELECT {CHUNK_COLS} FROM rag_chunks WHERE project_id = ? AND id IN ({marks})", (project_id, *ids))
        return {r[0]: _row(r) for r in rows}

    def neighbor(self, project_id: str, path: str, idx: int) -> dict | None:
        rows = self._q(f"SELECT {CHUNK_COLS} FROM rag_chunks WHERE project_id = ? AND path = ? AND idx = ?", (project_id, path, idx))
        return _row(rows[0]) if rows else None

    def lexical_candidates(self, project_id: str, terms: list[str], limit: int = 400) -> list[dict]:
        terms = [t for t in terms if t.isalnum() or t.replace("_", "").isalnum()][:8]
        if not terms:
            return []
        cond = " OR ".join("LOWER(text) LIKE ?" for _ in terms)
        rows = self._q(f"SELECT {CHUNK_COLS} FROM rag_chunks WHERE project_id = ? AND ({cond}) LIMIT ?",
                       (project_id, *[f"%{t}%" for t in terms], limit))
        return [_row(r) for r in rows]

    def stats(self, project_id: str) -> dict:
        f = self._q("SELECT COUNT(*) FROM rag_files WHERE project_id = ?", (project_id,))[0][0]
        c = self._q("SELECT COUNT(*) FROM rag_chunks WHERE project_id = ?", (project_id,))[0][0]
        return {"files": f, "chunks": c}

    # ---------- memorias
    def add_memory(self, mid: str, project_id: str, kind: str, text: str, source: str, created_iso: str) -> None:
        self._x("INSERT INTO project_memories (id, project_id, kind, text, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (mid, project_id, kind, text, source, created_iso))

    def list_memories(self, project_id: str, limit: int = 200) -> list[dict]:
        rows = self._q("SELECT id, kind, text, source, created_at FROM project_memories WHERE project_id = ? "
                       "ORDER BY created_at DESC LIMIT ?", (project_id, limit))
        return [dict(zip(("id", "kind", "text", "source", "created_at"), r)) for r in rows]

    def delete_memory(self, project_id: str, mid: str) -> bool:
        return self._x("DELETE FROM project_memories WHERE project_id = ? AND id = ?", (project_id, mid)) > 0

    def purge_memories_before(self, project_id: str, cutoff_iso: str) -> int:
        return self._x("DELETE FROM project_memories WHERE project_id = ? AND created_at < ?", (project_id, cutoff_iso))
