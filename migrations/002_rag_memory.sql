-- 002: índice RAG por proyecto y memoria de proyecto. Solo AÑADE tablas; no toca datos existentes.
-- Sustituye en la práctica a knowledge_sources (que se conserva sin cambios por compatibilidad).
CREATE TABLE IF NOT EXISTS rag_files (
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 path TEXT NOT NULL,
 sha256 TEXT NOT NULL,
 revision TEXT,
 size_bytes BIGINT NOT NULL,
 chunk_count INTEGER NOT NULL CHECK (chunk_count >= 0),
 indexed_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY (project_id, path)
);
CREATE TABLE IF NOT EXISTS rag_chunks (
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL,
 path TEXT NOT NULL,
 idx INTEGER NOT NULL CHECK (idx >= 0),
 start_line INTEGER NOT NULL,
 end_line INTEGER NOT NULL,
 symbol TEXT,
 kind TEXT NOT NULL,
 text TEXT NOT NULL,
 FOREIGN KEY (project_id, path) REFERENCES rag_files(project_id, path) ON DELETE CASCADE,
 UNIQUE (project_id, path, idx),
 CHECK (end_line >= start_line)
);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_project ON rag_chunks(project_id);
CREATE TABLE IF NOT EXISTS project_memories (
 id TEXT PRIMARY KEY,
 project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK (kind IN ('architecture','decision','modification','note')),
 text TEXT NOT NULL,
 source TEXT NOT NULL CHECK (source IN ('agent','user','system')),
 created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_project_memories_project_created ON project_memories(project_id, created_at);
