# Estado de conexión del runtime AXION con la API

## Estado verificado por inspección estática

- `agent/runtime.py` construye `CodingAgent` con `DbApprovalGate` y `RunStore`.
- `CodingAgent` dispone de `run`, `restore`, `continue_run` y `resume`.
- `RunStore` y `DbApprovalGate` usan `MetaStore`, que requiere una conexión DB-API y administra commit/rollback por operación.
- La API web usa SQLAlchemy `engine` y todavía no construye ni invoca el runtime persistente.
- `POST /workspace/agent/tasks` crea un plan con el planner y guarda una aprobación en la tabla legacy `approvals`. No crea un registro `agent_runs` ni ejecuta herramientas.
- `GET /workspace/agent/runs` y `GET /workspace/agent/runs/{run_id}` solo leen registros existentes y filtran por membresía/proyecto.
- Las aprobaciones de planes legacy y las aprobaciones de acciones son recursos diferentes. El endpoint `POST /workspace/agent/plan-approvals/{approval_id}` solo decide el plan y responde `execution=not_executed`.
- Las aprobaciones de acciones se guardan en `action_approvals`; la decisión sincroniza `agent_run_actions` y tampoco ejecuta la acción. El runtime aún no está conectado para canjear y aplicar la acción desde una petición autenticada.

## Por qué no se conectó todavía

No se debe adaptar `MetaStore` creando una conexión DB-API global tomada del pool SQLAlchemy: una conexión global compartida entre peticiones asíncronas puede cruzar transacciones, provocar concurrencia insegura y romper el ciclo de vida del pool. Tampoco es correcto llamar a `CodingAgent.resume()` antes de definir la construcción segura de herramientas, workspace y backend sandbox por proyecto.

## Requisitos para habilitar el runtime HTTP

1. Implementar un adaptador transaccional por operación que use una conexión SQLAlchemy obtenida dentro de su propio contexto, o reescribir los stores para recibir una unidad de trabajo explícita. No compartir conexiones entre peticiones.
2. Resolver el workspace desde configuración del servidor y un identificador de proyecto validado; nunca aceptar rutas locales del cliente. Verificar confinamiento real, symlinks y permisos del filesystem.
3. Construir herramientas para cada proyecto autenticado, sin compartir objetos Workspace/GitManager entre proyectos.
4. Exigir backend Docker aislado. No habilitar LocalBackend en producción: no aísla el filesystem.
5. Mantener red deshabilitada por defecto y comandos bloqueados fuera de la política. Las operaciones mutables deben producir propuestas y exigir aprobación ligada al hash exacto.
6. Diseñar la reconciliación tras interrupciones. Una acción en estado `running` nunca se reejecuta automáticamente.
7. Añadir pruebas HTTP de inicio, restauración, permisos, aprobación, rechazo, expiración, recuperación y aislamiento entre proyectos.
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

- Se inspeccionó `agent/workspace.py`: las rutas absolutas y los destinos resueltos fuera de la raíz del proyecto se rechazan; los symlinks que apuntan dentro del proyecto se resuelven al destino.
- Se añadió `tests/test_workspace_path_confinement.py` para cubrir traversal, symlinks externos en lectura/escritura y symlinks internos.
- La prueba es una regresión de la política existente; todavía no se ha ejecutado.
- **Riesgo residual importante:** la comprobación usa resolución de rutas seguida de operaciones de filesystem separadas. Un proceso local concurrente que pueda modificar el árbol del workspace podría intentar una carrera TOCTOU (cambiar symlinks/componentes entre validación y uso). Estas pruebas no eliminan ni demuestran ausencia de esa carrera.
- Antes de exponer herramientas de escritura a usuarios, sustituir las operaciones sensibles por acceso basado en descriptores de directorio (`openat`/equivalentes con `O_NOFOLLOW`), o ejecutar el workspace dentro de un volumen aislado cuya estructura no pueda modificar otro usuario/proceso; añadir pruebas de carrera en Linux.
- La configuración y el despliegue del backend Docker siguen sin verificarse; no se debe interpretar la existencia de `DockerBackend` como prueba de que la API lo usa correctamente.


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
- Este cambio es de fail-closed; no habilita red ni conecta el runtime HTTP. El backend Docker continúa sin estar configurado en Compose y no se ejecutó ningún contenedor real.


### Bloqueo reforzado de egress Docker

- La configuración ya no permite habilitar egress mediante un booleano ni mediante el nombre de una red Docker.
- Cualquier solicitud de ejecución Docker con `network=True` falla cerrada antes de invocar el daemon.
- Se añadieron pruebas para rechazar tanto la ejecución con red como los intentos de configurar `allow_egress` o una red egress.
- Esto no demuestra aislamiento de Docker en tiempo real: el daemon, los montajes y los límites siguen pendientes de integración en un entorno desechable.
