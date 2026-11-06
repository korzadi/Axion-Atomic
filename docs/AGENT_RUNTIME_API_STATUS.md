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
