# Conectar AXION ATOMIC con Qdrant Cloud

AXION ATOMIC usa **Qdrant Cloud administrado** como almacén vectorial. No se debe iniciar ni añadir un servidor Qdrant local al despliegue.

## Datos que se obtienen en Qdrant Cloud

1. Crear un clúster en el panel oficial de Qdrant Cloud: https://cloud.qdrant.io/
2. Copiar la URL HTTPS del clúster desde sus detalles de conexión.
3. Crear una API key con permisos de lectura y escritura sobre el clúster y guardarla en un gestor de secretos.
4. No publicar la API key en GitHub, tickets, capturas ni registros.

## Variables de entorno

Configurar estas variables en el entorno seguro donde se ejecutará la API:

- `QDRANT_URL`: URL HTTPS del clúster, sin sustituirla por localhost.
- `QDRANT_API_KEY`: API key privada del clúster.
- `QDRANT_COLLECTION`: nombre de colección; el valor inicial del proyecto es `qwen_knowledge`.
- `EMBED_DIMENSION`: dimensión del modelo de embeddings; el valor configurado es `768` para `nomic-embed-text`.

El archivo `.env.example` solo contiene marcadores de posición. Nunca copiar una API key real a ese archivo ni confirmar un archivo `.env` en Git.

## Comportamiento de AXION

- El cliente oficial `qdrant-client` se conecta mediante HTTPS y envía la API key.
- Si la colección no existe, AXION intenta crearla con vectores de 768 dimensiones y distancia cosine.
- Los registros se filtran por `project_id`; las fuentes también se identifican mediante `source_id`.
- La API devuelve errores genéricos al usuario y no debe registrar la API key ni el contenido sensible indexado.
- CI usa un doble de protocolo para probar el ciclo de fuentes sin iniciar un almacén local ni consumir un clúster remoto.

## Validación antes de producción

1. Confirmar URL y API key desde el entorno de pruebas, sin compartirlas en el chat ni en GitHub.
2. Ejecutar una prueba de conectividad autenticada contra el clúster.
3. Verificar creación de colección, inserción, búsqueda, aislamiento entre proyectos, reindexación y eliminación.
4. Revisar métricas y límites del plan del clúster.
5. No habilitar usuarios reales hasta superar estas comprobaciones.

**Estado:** el código está preparado para Qdrant Cloud. La prueba remota real queda pendiente de las credenciales del clúster de pruebas del operador.


## Resultado de prueba remota — 6 de noviembre de 2026

La validación que antes figuraba como pendiente se completó en GitHub Actions, run [42295136956](https://github.com/korzadi/Axion-Atomic/actions/runs/42295136956), job `qdrant-cloud-integration`, con resultado **success**:

- Conexión HTTPS autenticada a Qdrant Cloud.
- Creación de colección temporal de prueba.
- Inserción de vectores.
- Búsqueda filtrada por `project_id`.
- Verificación de aislamiento entre proyectos.
- Eliminación filtrada de puntos.
- Eliminación final de la colección temporal creada por el propio job.

La prueba terminó con el mensaje: `PASS: Qdrant Cloud autenticado; crear, insertar, buscar, aislar proyectos y borrar puntos.` La colección temporal fue eliminada. No se usó Qdrant local ni se modificaron colecciones preexistentes.

**Límites:** esta prueba no sustituye una prueba completa de reindexación de documentos ni valida todavía la configuración de ejecución del VPS. No se ha desplegado ni cambiado infraestructura. Mantener las credenciales únicamente en secretos/variables protegidos; nunca imprimir la API key.
