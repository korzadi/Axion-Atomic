-- REVERSIÓN MANUAL de 002. DESTRUCTIVA (borra el índice RAG y la memoria de proyecto).
-- No la ejecuta el migrador; requiere autorización expresa del propietario y copia de seguridad previa.
DROP TABLE IF EXISTS project_memories;
DROP TABLE IF EXISTS rag_chunks;
DROP TABLE IF EXISTS rag_files;
DELETE FROM schema_migrations WHERE version = '002';
