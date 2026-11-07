# Estado real del proyecto AXION ATOMIC

**Rama revisada:** `main`  
**Estado:** desarrollo/hardening; NO apto para producción.  
**Alcance:** inspección estática del repositorio y cambios de código/documentación mediante GitHub. No se ejecutaron pruebas localmente, contenedores, migraciones ni despliegues. La CI del commit `c4e72b7` terminó correctamente; los commits posteriores deben verificarse por separado.

## Identidad y restricciones confirmadas

- Producto: AXION ATOMIC.
- Agente: AXION.
- Modelo objetivo: ATOMIC CODE 1.1.
- Interfaz propia: AXION STUDIO.
- Ollama existente se trata como servicio externo; no instalar, actualizar ni alterar sus datos.
- No se integra ni depende de Open WebUI.
- No se accede al VPS, no se despliega, no se ejecutan migraciones ni se modifican secretos.
- El trabajo de implementación continúa sobre `main`, sin operaciones de infraestructura.

## Implementado (inspección estática; validación de ejecución pendiente)

- Filtro de recuperación Qdrant por `project_id` y validación de ese identificador.
- API key con fallo cerrado cuando no existe o es débil, y comparación de tiempo constante.
- GitManager con preview de archivos untracked, selección explícita de rutas y detección de patrones de secretos.
- Persistencia de ejecuciones/acciones y protección contra reutilizar el mismo hash con una carga útil distinta.
- Actualización condicional de aprobaciones y expiración.
- Health endpoint que consulta PostgreSQL, Ollama y Qdrant.
- Dockerfile copia los módulos internos requeridos y mantiene las migraciones como operación administrativa explícita.
- Contrato y estado comercial/técnico QvaPay documentados. El estado comercial se describe como APPROVED según confirmación del operador; la integración técnica sigue pendiente.
- Autenticación web con sesiones, cookies HttpOnly, CSRF, membresías de proyecto y roles de proyecto; permanece cerrada por defecto mediante `AUTH_ENABLED=false`.
- AXION STUDIO dispone de shell web público, formulario de login/registro y navegación de workspace.
- La vista Proyectos usa las rutas autenticadas reales para listar y crear proyectos; el backend asigna el rol owner al creador.
- FastAPI monta `frontend/` en la ruta raíz mediante `StaticFiles`, después de las rutas API. El Dockerfile copia el directorio frontend a la imagen. La entrega real empaquetada aún necesita verificación de CI/build y prueba en entorno autorizado.

## Bloqueadores y riesgos antes de producción

### 1. Identidad, sesiones y autorización multiusuario

El backend contiene autenticación web y autorización por membresía de proyecto, pero el interruptor global sigue deshabilitado. No se debe habilitar hasta completar verificación de correo, controles antiabuso y pruebas negativas de aislamiento. No existe todavía verificación/envío de correo, recuperación de contraseña, MFA ni rate limiting distribuido confirmado. OAuth Google/GitHub no está implementado. Una API key global identifica al servicio, no a una persona, por lo que las rutas legacy `/v1/*` no deben exponerse como API multiusuario.

### 2. AXION STUDIO y entrega

El frontend ya existe como archivo estático `frontend/Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html` y ahora está conectado al servidor FastAPI y al Dockerfile. Esto corrige la brecha previa en la que el archivo no se servía ni se empaquetaba. Aún falta verificar mediante CI y prueba de imagen que la ruta raíz se entregue correctamente en el artefacto final. Los módulos Chat, Modelos, Agentes, Atomic Code, Atomic Video y Conocimiento siguen siendo principalmente vistas informativas; no declarar sus flujos operativos. Administración no tiene API global ni RBAC superadmin verificado.

### 3. Agente, ejecuciones y aprobaciones

Las rutas `/workspace/agent/tasks` todavía crean un plan y una aprobación; esto no demuestra ejecución de herramientas. Existen rutas de lectura de ejecuciones persistidas y decisiones de aprobación, pero el ciclo de vida completo del `CodingAgent`/runtime —inicio, restauración, reanudación, cancelación, reconciliación y entrega de resultados— debe verificarse y conectarse de forma explícita. No afirmar ejecución real desde la API mientras no exista evidencia end-to-end. Las aprobaciones deben seguir vinculadas a payload/hash, proyecto, actor autorizado y expiración.

### 4. Aislamiento y sandbox

El aislamiento RAG por proyecto no reemplaza autorización. Falta demostrar que workspace, Git y sandbox siempre derivan el proyecto del usuario autenticado. Revisar el backend real del sandbox y verificar límites de CPU/RAM/tiempo/tamaño, políticas de red, cuotas y protección contra traversal, symlinks y escape. Mantener herramientas mutables deshabilitadas hasta validar el aislamiento en entorno separado.

### 5. Modelo

La configuración de Ollama apunta a un nombre de modelo, pero no se ha verificado desde esta rama que el servicio cargue ATOMIC CODE 1.1 ni que tokenizer/contexto/plantilla sean compatibles. Falta prueba de inferencia, evaluación reproducible, límites de contexto, cancelación, streaming y selección de modelos. No afirmar que el modelo fue ejecutado o validado. Ollama se mantiene externo y no debe modificarse en esta fase.

### 6. QvaPay y facturación

El estado comercial se documenta como **APPROVED** según confirmación del operador. La integración técnica sigue pendiente: Payment Manager, persistencia de facturas/transacciones, webhook firmado, consulta server-to-server, conciliación, idempotencia, ledger inmutable, créditos, suscripciones, cancelaciones, reembolsos y pruebas en sandbox. No realizar cobros reales ni alterar cuentas de pago.

### 7. Privacidad, legal y confianza

Faltan textos legales revisados por asesoría competente, jurisdicción y operador confirmados, política de retención, exportación/eliminación, consentimiento de cookies, inventario de encargados/subencargados, evaluación de SDKs, proceso de incidentes, accesibilidad auditada y datos comerciales verificables. No inventar domicilio, entidad legal, certificaciones, reseñas ni garantías.

### 8. Operación y observabilidad

El health endpoint básico no equivale a monitorización completa. Faltan escaneo de dependencias/SAST/secrets, cobertura y calidad frontend, backups y restauración probada, métricas, trazas, alertas, rate limits, cuotas y runbooks. La CI de Python que pasó para `c4e72b7` no demuestra que los cambios posteriores de frontend/Dockerfile hayan pasado; comprobar el run más reciente antes de cerrar esta fase.

## Secuencia de trabajo recomendada

1. Confirmar CI de los commits de integración de AXION STUDIO y corregir cualquier fallo de pruebas.
2. Verificar la entrega estática de la página raíz y la precedencia de rutas API con pruebas automatizadas.
3. Completar seguridad de identidad: correo, recuperación, rate limiting y pruebas de sesión/CSRF; mantener auth cerrada mientras tanto.
4. Completar aislamiento multiusuario/proyecto en RAG, Git, sandbox y almacenamiento de ejecuciones.
5. Conectar el runtime persistente del agente y el ciclo de aprobaciones con pruebas end-to-end, manteniendo ejecución mutable bajo aprobación explícita.
6. Conectar módulos de AXION STUDIO progresivamente a APIs reales; implementar roles globales antes del panel administrativo.
7. Completar Payment Manager/QvaPay en modo de pruebas y ledger.
8. Completar privacidad, accesibilidad, seguridad, CI y observabilidad.
9. Revisar migraciones y backups en un entorno aislado; realizar despliegue únicamente con aprobación expresa.
10. Entregar informe de release con resultados verificables. La existencia de código o documentación no sustituye las pruebas ni la aprobación de despliegue.

## Condiciones que requieren información/decisión del operador

No bloquear el trabajo técnico por estas preguntas: mantener los campos como pendientes hasta el momento en que sean necesarios.

- Nombre legal del operador/entidad y jurisdicción contractual.
- Dirección y datos fiscales/comerciales que deban publicarse.
- Países y edades admitidos, monedas, reglas de impuestos y política de reembolsos.
- Planes, precios, límites de uso y reglas de vencimiento de créditos.
- Política de retención y plazos de eliminación.
- Dominios definitivos de producción y remitente de correo.
- Si AXION puede aplicar cambios locales automáticamente después de aprobación o si cada cambio debe requerir confirmación individual (recomendación: confirmación individual para efectos mutables).

## Criterio de finalización

El proyecto solo podrá etiquetarse como listo cuando las pruebas automatizadas se hayan ejecutado y pasado para el commit de release, el aislamiento multiusuario esté demostrado, el sandbox se haya probado, las integraciones externas se hayan conciliado en modo de pruebas, las migraciones estén revisadas y exista un despliegue aprobado y verificable. La documentación o la existencia de código no sustituyen esas evidencias.


## Revisión estática ampliada del runtime y sandbox (6 de noviembre de 2026)

Esta sección registra una inspección adicional de `api/workspace_routes.py`, `agent/coding_agent.py`, `agent/run_store.py`, `agent/approval_gate.py`, `agent/approval_store.py`, `agent/toolset.py`, `agent/workspace.py`, `agent/git.py`, `sandbox/executor.py`, `sandbox/policy.py`, `sandbox/backends.py`, `sandbox/runner.py` y `sandbox/snapshot.py`. Es una revisión de código, no una prueba de ejecución.

### Hallazgos concretos del runtime

- `CodingAgent` ya implementa un bucle de modelo/herramienta, validación de argumentos, observaciones redactadas, límites de pasos/repeticiones y eventos.
- Las herramientas mutables de archivos y Git se representan como propuestas; el agente pausa en `awaiting_approval` y valida el hash antes de aplicar.
- `RunStore` persiste ejecuciones y acciones por proyecto, evita reutilizar un hash con otra carga útil y marca acciones reclamadas como `running`. Una acción que quedó en ese estado requiere reconciliación humana y no se repite automáticamente.
- `DbApprovalGate` ofrece aprobación persistente con expiración, decisión condicional y canje de un solo uso ligado al hash.
- La ruta HTTP `POST /workspace/agent/tasks` todavía llama al planificador y crea una aprobación de plan; no instancia ni ejecuta `CodingAgent`. Las rutas de aprobación HTTP actualizan registros, pero devuelven expresamente `execution: not_executed`. Por tanto, el runtime existe como componentes, pero el flujo web end-to-end aún no está conectado.
- No se encontró en las rutas workspace revisadas una operación HTTP para iniciar, reanudar, cancelar o reconciliar una ejecución del `CodingAgent`. La cancelación y la recuperación operacional siguen pendientes.
- Debe verificarse en el punto de composición de la aplicación que la misma instancia/configuración persistente de `DbApprovalGate` se comparte entre el runtime y las decisiones HTTP. No asumir que el registro aprobado por la API es visible para una puerta en memoria.

### Hallazgos concretos del sandbox

- `SandboxExecutor` trabaja sobre una copia temporal del proyecto; el snapshot excluye archivos sensibles/ignorados, omite symlinks y tiene límites predeterminados de 200 MB y 20.000 archivos.
- `DockerBackend` aplica límites de CPU, memoria, PIDs, tiempo y salida; usa root filesystem de solo lectura, usuario no root, capacidades eliminadas, `no-new-privileges` y red Docker `none`.
- El backend Docker rechaza explícitamente cualquier configuración de egress porque no existe una política de salida de red verificada. Los comandos que requieren red no deben considerarse ejecutables en el backend de producción.
- `LocalBackend` no aísla el sistema de archivos y exige un opt-in explícito de desarrollo. No es un backend aceptable para producción.
- La política de comandos bloquea comandos privilegiados, Docker, Git, shells y rutas absolutas/traversal; los comandos no reconocidos o con red requieren aprobación, pero la aprobación no elimina las restricciones del backend.
- Estos controles son prometedores en el código, pero faltan pruebas de integración del backend Docker real, comprobaciones de configuración efectiva, pruebas de escape/aislamiento y auditoría del entorno donde se ejecutaría.

### Próximos trabajos técnicos priorizados

1. Inspeccionar el punto de composición/DI de FastAPI y las fábricas de runtime para demostrar que `Workspace`, `GitManager`, `SandboxExecutor`, `RunStore` y `DbApprovalGate` se construyen por proyecto y con la misma persistencia.
2. Diseñar una capa de servicio de ejecuciones que derive el proyecto y el actor exclusivamente de la sesión autenticada; no aceptar rutas de workspace ni identidades arbitrarias del cliente.
3. Añadir endpoints autenticados para crear, consultar, reanudar y cancelar ejecuciones solo después de definir la semántica de concurrencia, idempotencia y reconciliación.
4. Unificar las aprobaciones de plan legado y las aprobaciones de acciones del runtime, o documentar claramente sus contratos separados. No permitir que una aprobación de plan autorice una herramienta.
5. Añadir pruebas de integración que cubran: proyecto ajeno, actor sin rol, CSRF, aprobación expirada, hash incorrecto, doble canje, reinicio con acción `running`, reanudación tras aprobación y ausencia de reejecución duplicada.
6. Añadir pruebas del sandbox para red deshabilitada, límites de recursos, timeout, truncamiento, limpieza de contenedor/snapshot, symlinks, archivos sensibles y backend local rechazado por defecto.
7. Solo tras esas pruebas, conectar las vistas de AXION STUDIO al ciclo real de ejecución.

### Estado de CI revisado en esta pasada

- La rama `main` tiene como commits más recientes `89c3922` (documentación) y `f5f1927` (chat de AXION STUDIO).
- La consulta de estados de commit no devolvió status checks para ninguno de esos dos commits. Esto no demuestra éxito ni fallo de GitHub Actions; el resultado debe quedar como **CI no confirmado** hasta consultar los runs y sus jobs.
- No se ejecutaron pruebas locales ni se construyó una imagen Docker durante esta revisión.


### Hallazgo adicional: identidad del modelo y API heredada

- `api/config.py` declara como modelo predeterminado `atomic-code:16k-8k` y `num_ctx=16384`; sin embargo, la respuesta de `/workspace/chat/completions` etiqueta el resultado como `ATOMIC CODE 1.1`. Esa etiqueta es texto fijo y no demuestra qué modelo respondió. Antes de anunciar compatibilidad con Atomic Code 1.1, el backend debe exponer el identificador configurado/real y validarlo sin alterar Ollama.
- La API heredada `/v1/*` está protegida además por `legacy_api_enabled=false` por defecto y exige una clave fuerte con comparación de tiempo constante cuando se habilita. Mantenerla cerrada para el navegador multiusuario; la clave compartida no representa identidad ni membresía de proyecto.
- `agent/runtime.py` sí contiene una composición de `CodingAgent` con `RunStore` y `DbApprovalGate` persistentes. Esto confirma que existe una fábrica del runtime, pero no la integración HTTP: la propia fábrica declara que no autentica, no autoriza, no crea workspaces ni activa endpoints. La capa de rutas debe construir herramientas confinadas después de autorizar al usuario y proyecto.


### Protección de cuotas del runtime de agente

La auditoría de rutas detectó que `/workspace/agent/runs` y `/workspace/agent/runs/{run_id}/resume` consumían el rate limit antes de validar la membresía del proyecto. Esto permitía a una cuenta ajena consumir el bucket asociado a un proyecto si conocía su identificador. Las dos rutas ahora autorizan primero (`owner`, `admin` o `editor`) y solo después consumen cuotas o construyen el runtime. Se añadieron pruebas HTTP que simulan una cuenta no miembro y verifican HTTP 403, cero consumo del rate limit y cero invocaciones del runtime. Pendiente validar el resultado en CI.
