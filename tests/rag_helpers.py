import math
import sqlite3
from pathlib import Path

from core.errors import TransportError
from rag.lexical import tokenize
from rag.meta import MetaStore

DIM = 64


class HashEmbedder:
    """Doble de prueba determinista (bolsa de palabras hasheada). NO mide calidad semántica real."""
    dimension = DIM

    def __init__(self):
        self.calls = 0

    async def embed(self, texts):
        self.calls += 1
        out = []
        for t in texts:
            v = [0.0] * DIM
            for tok in tokenize(t):
                v[hash_tok(tok) % DIM] += 1.0
            out.append(v)
        return out


def hash_tok(tok: str) -> int:
    h = 0
    for ch in tok:
        h = (h * 131 + ord(ch)) % 1_000_003
    return h


class FailingEmbedder:
    dimension = DIM

    async def embed(self, texts):
        raise TransportError("ollama caído", retryable=False)


MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def make_meta(projects=("p1", "p2"), db_path: str = ":memory:") -> MetaStore:
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT)")
    for p in projects:
        conn.execute("INSERT INTO projects VALUES (?, ?)", (p, p))
    # se ejecutan los archivos de migración REALES, no un esquema paralelo
    for name in ("002_rag_memory.sql", "003_approvals_audit.sql"):
        conn.executescript((MIGRATIONS / name).read_text())
    conn.commit()
    return MetaStore(conn, "?")


def open_meta(db_path: str) -> MetaStore:
    """Otra conexión a la misma base (para probar concurrencia entre 'procesos')."""
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    return MetaStore(conn, "?")
