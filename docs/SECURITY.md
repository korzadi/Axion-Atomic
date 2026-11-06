# Seguridad y límites conocidos

Este starter no está endurecido para producción.
- API key simple; rotar antes de usar y añadir TLS, rate limiting y auditoría.
- Mantener API, PostgreSQL y Qdrant privados.
- Sin Docker socket ni montaje del home del host.
- Ejecución de comandos deliberadamente deshabilitada.
- La aprobación solo registra la decisión; no ejecuta acciones.
- Antes de ejecutar código: sandbox efímero no privilegiado, límites CPU/RAM/tiempo/red, filesystem aislado y sin secretos.
- Vincular aprobación a hash inmutable del diff/acción para evitar TOCTOU.
- Validar argumentos y rutas; tratar salidas del modelo y RAG como no confiables.
- No indexar `.env`, claves privadas, semillas, tokens, volcados de producción ni datos personales.
