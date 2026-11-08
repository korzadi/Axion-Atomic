# Estado de conexión del runtime AXION con la API

## Estado verificado por inspección estática

- `agent/runtime.py` construye `CodingAgent` con `DbApprovalGate` y `RunStore`.
- `CodingAgent` dispone de `run`, `restore`, `continue_run` y `resume`.
- `RunStore` y `DbApprovalGate` usan `MetaStore`, que requiere una conexión DB-API y administra commit/rollback por operación.
- La API web usa SQLAlchemy `engine` y construye el runtime persistente mediante `ProjectAgentRuntime`, `build_authorized_project_toolset` y `SqlAlchemyMetaStore`.
- `POST /workspace/agent/tasks` crea un plan con el planner y guarda una aprobación en la tabla legacy `approvals`. No crea un registro `agent_runs` ni ejecuta herramientas.
- `GET /workspace/agent/runs` y `GET /workspace/agent/runs/{run_id}` solo leen registros existentes y filtran por membresía/proyecto.
- Las aprobaciones de planes legacy y las aprobaciones de acciones son recursos diferentes. El endpoint `POST /workspace/agent/plan-approvals/{approval_id}` solo decide el plan y responde `execution=not_executed`.
- Las aprobaciones de acciones se guardan en `action_approvals`; la decisión sincroniza `agent_run_actions` y tampoco ejecuta la acción. La reanudación autenticada canjea la aprobación y aplica la herramienta una sola vez; si el estado es incierto, exige reconciliación humana.

## Motivos de diseño del adaptador (histórico)

Esta sección conserva las razones del adaptador inicial; el runtime ya está conectado. La regla de no compartir conexiones globales sigue vigente.

No se debe adaptar `MetaStore` creando una conexión DB-API global tomada del pool SQLAlchemy: una conexión global compartida entre peticiones asíncronas puede cruzar transacciones, provocar concurrencia insegura y romper el ciclo de vida del pool. Tampoco es correcto llamar a `CodingAgent.resume()` antes de definir la construcción segura de herramientas, workspace y backend sandbox por proyecto.

## Requisitos para habilitar el runtime HTTP

1. Implementar un adaptador transaccional por operación que use una conexión SQLAlchemy obtenida dentro de su propio contexto, o reescribir los stores para recibir una unidad de trabajo explícita. No compartir conexiones entre peticiones.
2. Resolver el workspace desde configuración del servidor y un identificador de proyecto validado; nunca aceptar rutas locales del cliente. Verificar confinamiento real, symlinks y permisos del filesystem.
3. Construir herramientas para cada proyecto autenticado, sin compartir objetos Workspace/GitManager entre proyectos.
4. Exigir backend Docker aislado. No habilitar LocalBackend en producción: no aísla el filesystem.
5. Mantener red deshabilitada por defecto y comandos bloqueados fuera de la política. Las operaciones mutables deben producir propuestas y exigir aprobación ligada al hash exacto.
6. Diseñar la reconciliación tras interrupciones. Una acción en estado `running` nunca se reejecuta automáticamente.
7. Añadir pruebas HTTP de inicio, restauración, permisos, aprobación, rechazo, expiración, recuperación, cancelación y aislamiento entre proyectos.
8. Probar migraciones y el flujo completo en un entorno de prueba con datos descartables antes de cualquier despliegue aprobado.

## Estado de seguridad

- Autenticación web permanece desactivada por defecto (`AUTH_ENABLED=false`).
- Sin verificación de correo, rate limiting distribuido, MFA ni recuperación de cuenta, no habilitar autenticación para producción.
- Las rutas de lectura de ejecuciones no inician ni reanudan ejecuciones.
- No se han ejecutado pruebas, migraciones, imágenes Docker ni despliegues como parte de esta revisión.
- Este documento describe el estado del código; no constituye una certificación de seguridad ni una declaración de preparación para producción.


## Adaptador de persistencia incorporado

- Se añadió `agent/sqlalchemy_meta.py`: adapta el contrato DB-API de `MetaStore` a un SQLAlchemy Engine.
- Cada operación obtiene una conexión DB-API del pool, crea y cierra su cursor, confirma o revierte y devuelve la conexión al pool.
- No mantiene una conexión global compartida entre peticiones.
- `agent/runtime.py` incorpora `build_coding_agent_from_engine(...)` para construir el runtime con ese adaptador.
- Se añadió `tests/test_sqlalchemy_meta_store.py` para comprobar el ciclo de vida de conexión, conversión de placeholders y rollback mediante dobles de prueba.
- Estas pruebas se añadieron, pero no se han ejecutado en este entorno. El adaptador no equivale a una validación de integración contra PostgreSQL real.

El adaptador no autentica ni autoriza usuarios, no determina el directorio de trabajo, no crea un sandbox y no habilita endpoints HTTP. La conexión del runtime a la API sigue bloqueada hasta completar y probar el aislamiento de workspace, el backend Docker y el ciclo de aprobación/reconciliación.

## Revisión adicional de confinamiento de rutas

- Se inspeccionó `agent/workspace.py`: las rutas absolutas y el traversal se rechazan; las operaciones de lectura de archivos y aplicación de cambios abren cada componente de directorio mediante descriptores y `O_NOFOLLOW`.
- Los symlinks se rechazan incluso cuando apuntan dentro del proyecto. Esta política estricta evita depender de la resolución de destinos para operaciones sensibles.
- La escritura aprobada usa un archivo temporal creado con `O_EXCL | O_NOFOLLOW` dentro del descriptor del directorio y reemplazo relativo al mismo descriptor. La eliminación también es relativa al descriptor.
- Se ampliaron `tests/test_workspace_path_confinement.py` para cubrir symlinks de archivo, symlinks de directorio padre y symlinks internos.
- `list_dir` abre el directorio mediante descriptores y enumera entradas con `os.listdir(fd)` y `os.stat(..., follow_symlinks=False)`; omite symlinks y archivos especiales.
- `walk` recorre directorios abiertos con `O_DIRECTORY | O_NOFOLLOW`; `search` vuelve a abrir cada archivo mediante descriptor y aplica el límite global de lectura.
- Las lecturas parciales por rango de líneas también respetan `max_read_bytes`, evitando cargar archivos ilimitados en memoria.
- `apply` vuelve a calcular `before_sha` desde el descriptor del directorio que utilizará para `replace/unlink`, antes de mutar el destino.
- **Riesgo residual:** un proceso local hostil con permisos de escritura sobre el mismo directorio todavía podría competir en la estrecha ventana entre la última comprobación y `replace/unlink`; las primitivas portables usadas no proporcionan un compare-and-swap de nombre de archivo. El aislamiento de workspace por proyecto, permisos exclusivos y backend Docker siguen siendo requisitos antes de producción.
- Se añadieron pruebas para enumeración sin symlinks y para el límite de lectura en rangos parciales; el CI de código actualizado debe confirmarlas.


## Revisión del despliegue del sandbox Docker

La inspección estática de `Dockerfile`, `compose.yaml` y `sandbox/backends.py` identifica bloqueos concretos que impiden considerar operativo el backend Docker:

- La imagen de la API parte de `python:3.12-slim` e instala únicamente `requirements.txt`; no instala el cliente Docker.
- El servicio `api` de Compose no monta un socket Docker ni declara un endpoint de daemon. Por tanto, el proceso API no tiene un daemon configurado al que enviar `docker run`.
- `DockerBackend` monta en el daemon la ruta absoluta de un snapshot creado por el proceso API. Si se añade un daemon externo o en otro contenedor, esa ruta debe existir y ser accesible desde el host del daemon; compartirla no está configurado ni demostrado.
- El backend selecciona una red Docker llamada `axion-sandbox-egress` para ejecuciones con red. El nombre de una red bridge no demuestra filtrado de salida ni una allowlist de destinos. Las acciones que necesitan red deben seguir deshabilitadas hasta definir y probar una política de egress real.
- `LocalBackend` no aísla el filesystem y no es una alternativa aceptable para producción.

### Condiciones antes de conectar el runtime

1. Elegir explícitamente el modelo operativo del daemon (socket del host, daemon dedicado o servicio remoto). No montar el socket privilegiado del host como solución automática: concedería a la API una capacidad equivalente a control amplio del host.
2. Si se usa daemon externo, diseñar un mecanismo seguro de transferencia/montaje del snapshot y verificar que el path es visible desde el daemon. Añadir una prueba de integración que ejecute un contenedor efímero y compruebe que solo ve el snapshot previsto.
3. Incorporar el cliente Docker de forma reproducible en la imagen y configurar el endpoint de daemon explícitamente; comprobar disponibilidad al iniciar el backend, sin degradar silenciosamente a `LocalBackend`.
4. Mantener `--network none` como único modo habilitado inicialmente. Antes de permitir red, implementar una red de egress con reglas de salida verificables (DNS, IP, puertos y destinos), protección contra acceso a metadata/servicios internos y pruebas negativas.
5. Probar permisos UID/GID, lectura/escritura de snapshots, límites de CPU/RAM/PIDs, timeout, limpieza de contenedores y ausencia de procesos huérfanos en un entorno desechable.

**Resultado:** el backend contiene parámetros de aislamiento útiles, pero la configuración actual del proyecto no demuestra que pueda ejecutarse desde la API. No conectar herramientas de ejecución ni habilitar endpoints de runtime hasta cerrar y probar todos los puntos anteriores. Esta revisión fue estática; no se ejecutó Docker ni se modificó infraestructura.


## Endurecimiento adicional: salida de red del sandbox

- `DockerBackend` rechaza toda ejecución solicitada con red. Se eliminó el opt-in `allow_egress`; también rechaza configuraciones que intenten proporcionar una red egress. No existe un mecanismo para habilitar salida de red hasta implementar y verificar una política real.
- `LocalBackend` ya no interpreta silenciosamente la ausencia de `unshare` o de permisos para crear namespaces como si la red estuviera aislada. Si no puede crear el namespace de red y no existe una excepción explícita reservada a pruebas/desarrollo, rechaza la ejecución.
- Las pruebas locales que necesitan red declaran ahora de forma explícita `AXION_ALLOW_UNSAFE_LOCAL_NETWORK=1`. Esa excepción no debe configurarse en producción.
- Este cambio es de fail-closed; no habilita red. El backend Docker puede inyectarse con configuración explícita, pero no está configurado en Compose y no se ejecutó ningún contenedor real.


### Bloqueo reforzado de egress Docker

- La configuración ya no permite habilitar egress mediante un booleano ni mediante el nombre de una red Docker.
- Cualquier solicitud de ejecución Docker con `network=True` falla cerrada antes de invocar el daemon.
- Se añadieron pruebas para rechazar tanto la ejecución con red como los intentos de configurar `allow_egress` o una red egress.
- Esto no demuestra aislamiento de Docker en tiempo real: el daemon, los montajes y los límites siguen pendientes de integración en un entorno desechable.


## Auditoría de límites entre API de servicio y API multiusuario

- Las rutas heredadas `/v1/chat/completions`, `/v1/knowledge/ingest`, `/v1/agent/tasks` y `/v1/agent/approvals` se protegen con una única API key de servicio. Esa clave autentica al servicio, pero no identifica a un usuario ni comprueba una membresía de proyecto.
- Por ello, esas rutas no deben exponerse directamente a clientes finales ni a Internet como sustituto de las rutas `/workspace/*`. La API key debe permanecer en un backend de confianza y los proyectos deben tratarse como un límite de seguridad.
- La API heredada usa el identificador `service-api` como revisor en decisiones de aprobación; no equivale a una aprobación atribuible a una persona. No debe interpretarse como auditoría humana individual.
- Las rutas `/workspace/*` sí exigen sesión, CSRF en operaciones mutables y comprobación de membresía/rol del proyecto. Aun así, autenticación sigue desactivada por defecto y no se debe habilitar para producción sin verificación de correo, rate limiting distribuido, MFA y recuperación segura.
- La ruta `/health` consulta y revela el estado general de PostgreSQL, Ollama y Qdrant. Antes de publicar la API, limitar su exposición o devolver únicamente un estado agregado sin detalles de dependencias.
- No se cambió el comportamiento de estas rutas en esta fase. El objetivo de esta anotación es dejar explícito el límite de confianza y evitar que una API key global se confunda con autorización multiusuario.



## Auditoría del RAG utilizado por las rutas multiusuario

- `POST /workspace/knowledge/ingest` y `POST /workspace/chat/completions` llaman actualmente a `rag.service` (Qdrant directo), no al pipeline más reciente `RepoIndexer` / `Retriever`.
- El filtro `project_id` se aplica tanto al guardar como al recuperar, y la recuperación vuelve a comprobar el proyecto del payload. Esto reduce el riesgo de mezcla entre proyectos, pero no resuelve el manejo de secretos.
- `IngestRequest` permite hasta 100.000 caracteres y `ingest_text` divide, genera embeddings y guarda el texto original en Qdrant sin pasar por `find_secrets` / `redact`. Un usuario podría indexar accidentalmente claves, tokens, datos personales u otros contenidos sensibles. La protección de secretos del `RepoIndexer` no se aplica a esta ruta.
- La llamada al cliente Qdrant es síncrona dentro de funciones `async`; puede bloquear el event loop bajo carga. La ruta captura excepciones de recuperación y devuelve contexto vacío, ocultando fallos operativos al usuario y reduciendo observabilidad.
- El campo `source` acepta texto libre de hasta 500 caracteres. Debe tratarse como dato no confiable y no como ruta o identidad verificada del origen.

### Remediación requerida antes de habilitar autenticación o publicar estas rutas

1. Aplicar detección de secretos y política de redacción/rechazo antes de generar embeddings y antes de persistir texto o metadatos. No basta con proteger solo la indexación de repositorios.
2. Añadir pruebas que demuestren que una cadena con un secreto sintético nunca llega al embedder ni a Qdrant, y que el aislamiento por proyecto se conserva.
3. Unificar la ruta manual con el pipeline RAG mantenido o documentar claramente sus garantías distintas; evitar dos implementaciones con políticas de seguridad divergentes.
4. Ejecutar operaciones Qdrant fuera del event loop o utilizar un cliente asíncrono; establecer límites de tiempo, tamaño total y cantidad de fragmentos.
5. Registrar fallos de recuperación de forma segura y devolver un estado degradado observable, sin exponer detalles internos ni secretos.

**Estado:** hallazgo estático confirmado en el código; no se modificó el comportamiento RAG ni se ejecutaron servicios. Las rutas web siguen cerradas por `AUTH_ENABLED=false` y no deben habilitarse hasta cerrar esta brecha.

## Matriz de autorización observada

- `viewer`: puede usar chat y consultar ejecuciones; no puede ingerir conocimiento, crear tareas ni decidir aprobaciones.
- `editor`: además puede ingerir conocimiento y crear solicitudes de plan; no puede aprobar planes ni acciones.
- `owner` / `admin`: pueden decidir aprobaciones de plan y de acción.
- La decisión de aprobación devuelve `execution=not_executed`; la aprobación no ejecuta herramientas por sí misma.
- No se encontraron rutas multiusuario para invitar, retirar o cambiar el rol de miembros. La gestión de membresías sigue siendo una capacidad pendiente, no debe suponerse implementada.
- Las pruebas actuales verifican el helper de autorización y el alcance de consultas de aprobaciones, pero todavía no constituyen una matriz HTTP completa para todos los roles y endpoints.




## Remediación aplicada: ingestión manual RAG

- `rag.service.ingest_text` valida texto, origen e identificador de proyecto antes de llamar a Qdrant o al modelo de embeddings.
- El contenido y el campo `source` se inspeccionan con el detector compartido `agent.secrets.find_secrets`. Si se detectan patrones de credenciales, la operación se rechaza con un error genérico que solo informa tipos y números de línea; nunca incluye el valor detectado.
- Se aplica un límite de 100.000 caracteres al texto y 500 al origen también en la capa de servicio, además de la validación del esquema HTTP.
- Las rutas de ingestión multiusuario y de servicio convierten la entrada rechazada en HTTP 422. No se persiste ni se genera embedding para ese contenido.
- `tests/test_rag_manual_ingest.py` añade cuatro pruebas: secreto sintético en texto, secreto en origen, ingestión válida con `project_id` preservado y rechazo de tamaño/proyecto inválidos. Las pruebas verifican que Qdrant y el embedder no se invocan en los dos casos de secreto.
- CI del commit `a00f19fc2e02a580738b33eb5a5dd46668b85f13` terminó correctamente: compilación y suite de pruebas (`python-tests: success`).

**Límites pendientes:** `find_secrets` es una heurística, no un detector universal; no debe prometerse que detecta todas las credenciales. La API de ingestión todavía usa llamadas síncronas del cliente Qdrant dentro de funciones `async`, por lo que su comportamiento bajo concurrencia/carga necesita una mejora y pruebas específicas. La ruta de recuperación también mantiene manejo degradado que oculta fallos Qdrant devolviendo contexto vacío. No se conectó el runtime ni se cambió infraestructura.



## Remediación aplicada: operaciones RAG fuera del event loop

- Las llamadas síncronas `ensure_collection`, `upsert` y `query_points` del cliente Qdrant se ejecutan mediante `asyncio.to_thread` para no bloquear el event loop de FastAPI mientras esperan operaciones de red.
- La recuperación ya no convierte cualquier excepción de Qdrant en contexto vacío. Lanza `KnowledgeStoreUnavailable` con un mensaje público genérico y registra un evento sin incluir detalles internos.
- Las rutas de chat heredada y multiusuario convierten ese estado en HTTP 503; no continúan la generación como si la recuperación hubiera funcionado correctamente.
- Se añadieron pruebas para confirmar que las operaciones síncronas de ingestión se ejecutan fuera del hilo del event loop y que un fallo de recuperación no se oculta ni filtra detalles internos.
- CI del commit `8feb350e136722ed56b41bcbd1159ca8d8a0f7b9` terminó correctamente: compilación y suite completa (`python-tests: success`).

**Límites pendientes:** `asyncio.to_thread` evita bloquear el event loop, pero no hace que el cliente Qdrant sea asíncrono ni elimina la necesidad de límites de concurrencia y timeout. Las pruebas usan dobles; todavía se necesita una prueba de integración contra Qdrant real en un entorno desechable. La generación de embeddings sigue siendo secuencial por fragmento. No se ha habilitado autenticación ni runtime HTTP.



## Verificación adicional del aislamiento en recuperación RAG manual

- Se añadió una prueba que simula una respuesta de Qdrant que contiene un resultado del proyecto autorizado y otro de un proyecto distinto.
- La prueba comprueba que la consulta incluye un filtro Qdrant exacto por `project_id` y que la capa de aplicación vuelve a validar el `project_id` del payload antes de construir el contexto.
- También comprueba que `query_points` se ejecuta fuera del hilo del event loop.
- CI del commit `18e99ec740c406de9ec2c1b8969f4c3a362cb1d1` terminó correctamente: compilación y suite completa (`python-tests: success`).

**Alcance de la prueba:** utiliza una respuesta simulada de Qdrant; demuestra el contrato de filtrado y la defensa adicional en la aplicación, pero no sustituye una prueba de integración con un servidor Qdrant real ni una revisión de credenciales/configuración del servicio.



## Bloqueos adicionales del flujo de identidad

- El registro crea usuarios con estado `pending_verification` y la autenticación solo acepta usuarios `active`.
- La migración contiene `email_verified_at`, pero en las rutas revisadas no existe un flujo para emitir, enviar, validar y consumir un token de verificación. Tampoco existe una ruta de recuperación/cambio de contraseña.
- Por tanto, el registro HTTP actual no permite completar por sí solo el alta de una cuenta utilizable. No se debe activar `AUTH_ENABLED` hasta diseñar e implementar verificación de correo con tokens de un solo uso, expiración, almacenamiento hash, invalidación y límites antiabuso.
- No se encontró rate limiting distribuido ni MFA. La autenticación permanece deshabilitada (`AUTH_ENABLED=false`); no se cambió ese valor.
- La prueba `test_workspace_authorization.py` verifica que el helper recibe el usuario autenticado y los roles solicitados, pero no ejecuta una matriz HTTP completa de cada endpoint para cada rol. Esa cobertura sigue pendiente.

**Decisión de seguridad:** no crear un mecanismo manual para marcar usuarios como `active` ni habilitar autenticación solo para sortear el bloqueo. La verificación debe ser un flujo verificable y auditable, no un cambio directo de estado.


## Estado actualizado: runtime persistente conectado a la API

La revisión del código actual confirma que el runtime de ejecuciones sí está conectado a `POST /workspace/agent/runs`, `POST /workspace/agent/runs/{run_id}/resume`, `POST /workspace/agent/runs/{run_id}/reconcile` y `POST /workspace/agent/runs/{run_id}/cancel`, a través de `ProjectAgentRuntime`, `build_authorized_project_toolset` y el adaptador SQLAlchemy de persistencia. El runtime verifica membresía antes de resolver el workspace, limita cada proyecto a su directorio privado y conserva el gate de aprobación por acción. El backend no permite reejecutar automáticamente acciones que quedaron en estado `running`; las marca para reconciliación humana.

La interfaz de Axyron Studio permite iniciar, reanudar, reconciliar y cancelar ejecuciones según el estado y el rol. El botón de reanudación se muestra a owner/admin/editor para ejecuciones `awaiting_approval`; la cancelación y la reconciliación se limitan a owner/admin. Si la aprobación sigue pendiente, el backend devuelve la ejecución sin aplicar nada; si una acción requiere reconciliación, la interfaz lo comunica y no intenta repetirla. Una ejecución cancelada no se reinicia.

**Limitación de ejecución:** por defecto el runtime HTTP construye el toolset sin backend Docker. Puede inyectarse con `SANDBOX_DOCKER_ENABLED=true` y un daemon dedicado, pero la configuración no está activada ni validada end-to-end. Las herramientas de lectura y cambios de archivos aprobados existen; no se debe describir la terminal/sandbox como disponible.

Pruebas: `tests/test_frontend_studio_spa.py` ahora exige la ruta de reanudación, el control de confirmación y el botón para ejecuciones pendientes de aprobación. Las pruebas HTTP existentes en `tests/test_workspace_agent_runtime_http.py` cubren inicio, reanudación, permisos, CSRF y fallos cerrados. La ejecución CI de este commit debe completar antes de considerar el cambio validado.


## Estado vigente de integración HTTP — 7 de noviembre de 2026

Esta actualización prevalece sobre las secciones históricas anteriores que indicaban que no existían rutas de inicio/reanudación. La rama actual incluye:

- `POST /workspace/agent/runs`: inicia una ejecución persistente con `ProjectAgentRuntime.start` después de validar membresía `owner/admin/editor` y rate limit.
- `POST /workspace/agent/runs/{run_id}/resume`: restaura por `run_id + project_id`, comprueba membresía y reanuda según el estado persistido.
- `GET /workspace/agent/runs` y `GET /workspace/agent/runs/{run_id}`: lectura restringida a miembros del proyecto.
- `POST /workspace/agent/approvals/{approval_id}`: aprobación/rechazo por owner/admin; actualiza en una transacción la solicitud y la acción persistida, sin ejecutar la mutación dentro de la petición de decisión.
- La siguiente petición autenticada de resume consulta `DbApprovalGate`, reclama la acción una sola vez, comprueba de nuevo el hash y aplica la herramienta aprobada. Estados inciertos no se reejecutan automáticamente.
- `agent/sqlalchemy_meta.py` adapta stores al SQLAlchemy Engine mediante conexiones/cursors por operación; no comparte una conexión global.
- La fábrica de proyecto solo acepta `DockerBackend` si se inyecta. `_agent_runtime()` lo inyecta solo con `SANDBOX_DOCKER_ENABLED=true` y configuración válida; por defecto expone herramientas de workspace/Git con aprobación, pero no ejecución de comandos/sandbox. La activación real sigue bloqueada hasta validar el daemon dedicado y las imágenes.
- `compose.yaml` no expone socket Docker ni endpoint daemon al servicio API. No habilitar `LocalBackend` en producción ni montar automáticamente el socket del host.

### Endurecimiento de autorización antes de cuotas

El 7 de noviembre se corrigió el orden de las rutas de inicio y reanudación: ambas llaman a `_project_role(..., ("owner", "admin", "editor"))` antes de consumir rate limit. Se añadieron pruebas para confirmar que una cuenta ajena recibe 403 y no consume cuota ni invoca el runtime. La corrección está pendiente de la ejecución CI más reciente para considerarse verificada.


## Estado actualizado de integración HTTP — 7 de noviembre de 2026

Esta sección prevalece sobre las observaciones históricas anteriores cuando describen etapas ya completadas:

- La API multiusuario ahora construye `ProjectAgentRuntime` después de validar sesión, CSRF (en operaciones mutables), membresía y rol del proyecto.
- `POST /workspace/agent/runs` inicia ejecuciones persistidas y `POST /workspace/agent/runs/{run_id}/resume` restaura y continúa ejecuciones por la combinación de ID y proyecto autorizado.
- Las rutas de listado y detalle siguen filtradas por proyecto. Las decisiones de aprobación se vinculan al hash de acción; aprobar no equivale por sí solo a ejecutar ni a reanudar.
- Si la restauración detecta una acción que quedó en estado `running`, la ejecución pasa a reconciliación humana y no vuelve a ejecutar esa acción automáticamente.
- La composición HTTP inyecta `DockerBackend` solo con `SANDBOX_DOCKER_ENABLED=true` y configuración válida; por defecto no lo hace. Las herramientas de lectura/escritura/Git con aprobación pueden estar disponibles, pero la ejecución de comandos/sandbox permanece desactivada y sin validación end-to-end. No se debe anunciar terminal ni ejecución arbitraria como capacidad disponible.
- La activación Docker sigue bloqueada por la elección y configuración segura del daemon, TLS/certificados, CLI en la API, imágenes digest y pruebas reales de aislamiento. La transferencia de snapshots ya usa tar por stdin hacia un tmpfs, sin bind mount. No montar el socket privilegiado del host ni usar `LocalBackend` como sustituto de aislamiento.
- La autorización de inicio/reanudación debe ocurrir antes del rate limit y de construir el runtime. La CI asociada al HEAD actual debe confirmar las pruebas de regresión antes de considerar este cambio verificado.
- `AUTH_ENABLED=false` continúa siendo el estado operativo informado; el código de runtime integrado no habilita por sí mismo el acceso público ni autoriza cambiar la configuración del VPS.

**Alcance de verificación:** esta actualización documenta la inspección del código de `main`. No certifica ejecución en VPS, Docker real, autenticación pública, ni aislamiento de contenedores.


## Endurecimiento del protocolo de respuesta del modelo — 7 de noviembre de 2026

La auditoría del parser de respuestas de AXYRON detectó que `parse_action` aceptaba el primer objeto JSON válido e ignoraba contenido adicional posterior. Eso permitía respuestas ambiguas con texto o incluso un segundo objeto JSON después de la acción interpretada.

Se endureció el parser:
- Rechaza cualquier contenido no vacío después del único objeto JSON.
- Conserva compatibilidad con un bloque Markdown JSON único y texto introductorio, sin aceptar un segundo objeto o instrucciones añadidas al final.
- Los casos ambiguos se convierten en error de formato y pasan por el límite existente de fallos de parseo; no se ejecuta una segunda acción escondida en el mismo mensaje.
- Se añadieron pruebas para texto final, objetos concatenados y bloques contradictorios.

Archivos: `agent/coding_agent.py` y `tests/test_coding_agent.py`.

### Validación CI del cambio

GitHub Actions run [42404444729](https://github.com/korzadi/Axion-Atomic/actions/runs/42404444729), asociado exactamente al HEAD `e045d10158163be198128bba2708c598d00da410`, terminó con **success**:
- Python: **664 passed, 9 skipped, 4 warnings**.
- Axyron Studio browser E2E: success.
- Build y smoke test de imagen: success.
- Migraciones PostgreSQL: success.
- Integración autenticada de Qdrant Cloud: success.

Esta CI valida los tests automatizados y los jobs declarados; no certifica ejecución del agente en el VPS ni habilita el sandbox Docker del runtime HTTP.


## Límites de tamaño de argumentos de herramientas — 7 de noviembre de 2026

La auditoría de validación encontró que los argumentos de tipo lista solo comprobaban que todos sus elementos fueran cadenas, sin limitar el número de elementos ni el tamaño agregado. Se añadió un límite de 1.000 elementos y un máximo agregado de 200.000 caracteres para listas, manteniendo la validación estricta de claves y tipos.

Se añadieron pruebas para:
- Rechazar listas con más de 1.000 elementos.
- Rechazar listas cuyo contenido agregado excede 200.000 caracteres.
- Aceptar listas pequeñas válidas.

Archivos: `agent/toolset.py` y `tests/test_coding_agent.py`.

GitHub Actions run [42404791578](https://github.com/korzadi/Axion-Atomic/actions/runs/42404791578), asociado al HEAD `e5838f711d2775452d707aee8607cd80cfa5b056`, terminó con **success** en los cinco jobs:
- Python: **665 passed, 9 skipped, 4 warnings**.
- Studio Browser E2E: success.
- Build/smoke de imagen: success.
- Migraciones y pruebas PostgreSQL: success (**46 passed**).
- Integración Qdrant Cloud: success.

Esta validación no prueba la ejecución del sandbox desde el runtime HTTP, inferencia real en VPS ni los flujos de autenticación pública.


## Validación estricta del planificador — 7 de noviembre de 2026

La auditoría encontró que `agent/planner.py` aceptaba cualquier lista de diccionarios, truncaba silenciosamente planes de más de ocho pasos y no validaba campos, niveles de riesgo ni tamaños. También devolvía texto bruto del modelo como supuesto plan de respaldo.

Corrección:
- Solo se aceptan planes JSON con entre 3 y 8 pasos.
- Cada paso debe contener exactamente `title`, `rationale`, `risk` y `proposed_action`.
- Riesgo limitado a `low`, `medium` o `high`.
- Límites de caracteres por campo y respuesta completa.
- Objetivos limitados a 10.000 caracteres.
- Ante respuesta inválida o fallo de inferencia, se devuelve un plan genérico de revisión; nunca se inserta texto bruto no validado del modelo.
- La validación no ejecuta acciones: la aprobación del plan sigue siendo un registro de intención y no ejecuta código.

Archivos: `agent/planner.py` y `tests/test_planner.py`.

La primera ejecución detectó un defecto en el fixture de pruebas (solo generaba tres pasos para probar el caso de cuatro); se corrigió el fixture y se volvió a ejecutar CI.

GitHub Actions run [42405182522](https://github.com/korzadi/Axion-Atomic/actions/runs/42405182522), HEAD `6a8d8564ed1ac653c79e426e778447394ef8ccdb`: **success**, cinco jobs aprobados. Python: **675 passed, 9 skipped, 4 warnings**; Studio Browser E2E, imagen, PostgreSQL y Qdrant Cloud: success.

Sigue pendiente la integración del sandbox Docker aislado en el runtime HTTP, además de pruebas end-to-end con inferencia real y autenticación pública.

## Endurecimiento del límite HTTP de ejecuciones — 8 de noviembre de 2026

Se corrigió el mapeo de errores de `POST /workspace/agent/runs` y `POST /workspace/agent/runs/{run_id}/resume`:

- `RunStore.get_run` distingue ahora `RunNotFoundError` de otros fallos de almacenamiento.
- Una ejecución inexistente o de otro proyecto devuelve HTTP 404 sin revelar detalles internos.
- Una aprobación inexistente, expirada o no canjeable devuelve HTTP 409 en lugar de un error 500 no controlado.
- Los errores de workspace no disponible siguen devolviendo 503 y los argumentos inválidos 422.
- Se añadieron pruebas unitarias para los códigos 404/409 y para la nueva excepción del store.

Verificación local: `812 passed, 9 skipped` con `python` disponible mediante un enlace temporal; las 9 omisiones son PostgreSQL. Sin ese enlace, `791 passed, 9 skipped` al excluir las 21 pruebas de sandbox local. El backend Docker ya puede inyectarse solo con configuración explícita y daemon dedicado; la activación real sigue bloqueada y no se modificó infraestructura.

## Reconciliación humana de acciones interrumpidas — 8 de noviembre de 2026

Se añadió `POST /workspace/agent/runs/{run_id}/reconcile` para cerrar el caso que antes quedaba bloqueado en `needs_reconciliation`:

- Exige sesión, CSRF, membresía `owner`/`admin` y rate limit `agent_decision`.
- Recibe `action_hash` (SHA-256 hexadecimal), `resolution` (`applied` o `failed`) y un motivo obligatorio de al menos 8 caracteres.
- Solo acepta la reconciliación si la ejecución está en `needs_reconciliation` y la acción concreta sigue en estado `running`.
- Actualiza la acción y la ejecución en una sola transacción; después deja la ejecución en `awaiting_approval` y no ejecuta ni repite la herramienta.
- Registra la decisión en la cadena `audit_log` dentro de la misma transacción. Si la cadena cambia o falla la auditoría, no se aplica la reconciliación.
- `CodingAgent.resume` ahora omite acciones persistidas como `failed`, `rejected` o `expired` aunque una aprobación antigua siga en estado `approved`; nunca las reintenta a ciegas.
- Axyron Studio muestra controles separados «Marcar aplicada» y «Marcar no aplicada» solo para owner/admin cuando la ejecución requiere reconciliación. La interfaz solicita un motivo y después pide reanudar explícitamente.

Pruebas añadidas: `tests/test_workspace_agent_reconciliation_http.py` y un caso de regresión en `tests/test_coding_agent_persistence.py`. Verificación local: `812 passed, 9 skipped` con `python` disponible; `791 passed, 9 skipped` sin las 21 pruebas de sandbox local. Compilación y sintaxis JS correctas.

## Sandbox Docker preparado para daemon dedicado — 8 de noviembre de 2026

Se eliminó la dependencia de un bind mount local en `DockerBackend`:

- El snapshot se serializa como tar y se transfiere por stdin a `docker run -i`; el contenedor lo extrae en un `tmpfs` privado `/workspace` (`uid`/`gid`/`mode=0700`) antes de ejecutar el comando.
- Esto permite usar un daemon remoto por `ssh://` o `tcp://` con TLS; no se acepta `unix:///var/run/docker.sock` ni una ruta de socket local.
- La configuración permanece desactivada por defecto (`SANDBOX_DOCKER_ENABLED=false`). Si se activa, `_agent_runtime` inyecta el backend; una configuración incompleta devuelve 503 y no construye herramientas de ejecución.
- `SANDBOX_DOCKER_IMAGES` exige imágenes fijadas por digest. Para `tcp://` se exige `SANDBOX_DOCKER_TLS_VERIFY=true` y `SANDBOX_DOCKER_CERT_PATH`; también se admite `ssh://`.
- La imagen de sandbox debe incluir `sh` y `tar`. La CLI Docker debe estar disponible en la imagen de la API y el daemon debe ser dedicado, no privilegiado en el host. `--pull=never` exige que las imágenes digest estén precargadas en el daemon; no se permite descarga implícita.
- La auditoría de `SandboxExecutor` redacta secretos del comando registrado, además de la redacción ya aplicada por el logger.
- Pruebas añadidas: serialización de snapshot sin symlinks, comandos sin bind mount, transferencia por stdin, limpieza del contenedor, configuración fail-closed, TLS obligatorio para TCP y redacción de secretos en auditoría.

**Sigue bloqueado:** no hay daemon dedicado, certificados, imágenes verificadas ni CLI Docker en la imagen actual; no se activó la configuración, no se construyó ninguna imagen y no se ejecutó un E2E real. AGT-04 no está verificada.

## Cancelación de ejecuciones pendientes — 8 de noviembre de 2026

Se añadió `POST /workspace/agent/runs/{run_id}/cancel` para que owner/admin cierren una ejecución que espera aprobación sin aplicar ninguna acción:

- Exige sesión, CSRF, membresía `owner`/`admin` y rate limit `agent_decision`; el motivo es obligatorio (mínimo 8 caracteres útiles).
- Solo acepta ejecuciones en `awaiting_approval`. Una ejecución `running` no se cancela por esta vía: primero debe terminar o quedar en un estado persistido reconciliable; `needs_reconciliation` se resuelve con `/reconcile`.
- En una sola transacción bloquea primero las aprobaciones y después las acciones, en orden determinista, para evitar deadlocks con la decisión de aprobación. Si alguna acción está `running`, rechaza la cancelación con 409 para no interrumpir una reanudación en curso. En caso contrario rechaza las aprobaciones pendientes o aprobadas, marca como `expired` las acciones pendientes/aprobadas, cambia la ejecución a `cancelled`, limpia `pending_actions` y registra `agent.run.cancel` en la cadena de auditoría.
- La migración `022_agent_run_cancellation.sql` amplía el CHECK de `agent_runs.status` con `cancelled`.
- Reanudar una ejecución cancelada devuelve el estado persistido sin reiniciar el modelo ni ejecutar herramientas. `RunStore.save_run` no puede sobrescribir una ejecución cancelada; si una reanudación concurrente intenta persistir después de la cancelación, la ruta devuelve 409.
- Axyron Studio muestra «Cancelar ejecución» solo a owner/admin y exige motivo y confirmación.

Pruebas añadidas: `tests/test_workspace_agent_cancellation_http.py` y un caso de regresión en `tests/test_project_agent_runtime.py`. Verificación local: `812 passed, 9 skipped` con `python` disponible; `791 passed, 9 skipped` sin las pruebas de sandbox local. Compilación y sintaxis JS correctas. La migración no se aplicó en ninguna base real y CI sigue sin confirmarse.
