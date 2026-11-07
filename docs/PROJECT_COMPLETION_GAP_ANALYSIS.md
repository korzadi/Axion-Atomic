# Estado real del proyecto AXYRON ATOMIC

**Rama revisada:** `main`  
**Estado:** desarrollo/hardening; NO apto para producción.  
**Alcance:** inspección estática del repositorio y cambios de código/documentación mediante GitHub. No se ejecutaron pruebas localmente, contenedores, migraciones ni despliegues. La CI del commit `c4e72b7` terminó correctamente; los commits posteriores deben verificarse por separado.

## Identidad y restricciones confirmadas

- Producto: Axyron Atomic.
- Agente: AXYRON.
- Modelo objetivo: Atomic Code 1.1.
- Interfaz propia: Axyron Studio.
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

Las rutas HTTP de ejecuciones persistentes ya incluyen inicio, lectura, aprobación y reanudación autenticada por proyecto. Esto no demuestra ejecución de comandos: la API no inyecta un backend Docker. La recuperación de acciones interrumpidas requiere reconciliación humana y no las repite automáticamente. La validación end-to-end de todos los estados sigue pendiente. Las aprobaciones deben permanecer vinculadas a payload/hash, proyecto, actor autorizado y expiración.

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


## Actualización de estado — 7 de noviembre de 2026

Esta sección prevalece sobre las observaciones históricas anteriores cuando exista contradicción. El repositorio ya no está en el estado descrito por la primera auditoría:

- Identidad vigente: producto **Axyron Atomic**, agente **AXYRON**, interfaz **AXYRON STUDIO**. El HTML principal conservado es `frontend/Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html`.
- Autenticación web incluye verificación de correo, recuperación, MFA, OAuth Google/GitHub, sesiones, CSRF, cookies seguras y rate limiting persistente en código. `AUTH_ENABLED` permanece desactivado en el entorno operativo; SMTP/OAuth/MFA reales todavía requieren aceptación en staging.
- El runtime persistente ya está conectado a rutas HTTP: `POST /workspace/agent/runs`, `POST /workspace/agent/runs/{run_id}/resume`, lecturas de runs y decisiones de aprobación. `/workspace/agent/tasks` sigue siendo el planificador legacy y no debe confundirse con la ejecución real.
- La construcción del runtime vuelve a autorizar la membresía y resuelve un workspace privado por proyecto. Las mutaciones de archivos/Git requieren propuesta y aprobación ligada al hash. La ejecución de comandos/sandbox no está conectada a la API: Compose no proporciona un daemon Docker al servicio API, y no se debe montar el socket privilegiado del host como atajo.
- El health/readiness verifica PostgreSQL, Ollama, los modelos de chat y embeddings configurados y Qdrant; Redis opcional puede degradar sin hacer fallar readiness crítica.
- GitHub Actions `42401140808` aprobó Python, Playwright, build/smoke de imagen, migraciones PostgreSQL y Qdrant Cloud para el commit `d3fe1f1f479fbdd890339158a75ac3c289a91637`.
- La auditoría del 7 de noviembre detectó que las rutas de inicio y reanudación del agente consumían cuotas antes de comprobar la membresía. Se corrigió el orden: autorización `owner/admin/editor` antes del rate limit y antes de construir el runtime. Se añadieron pruebas negativas que comprueban HTTP 403 y que no se consume la cuota ni se inicia el runtime para usuarios externos. La ejecución CI de esta corrección aún debe quedar verde antes de marcarla verificada.

### Pendientes reales que siguen bloqueando V1.0

1. Validar las nuevas pruebas y la secuencia completa de aprobación/reanudación contra PostgreSQL real en CI; mantener pendiente una prueba end-to-end de agente con workspace aislado.
2. Definir y probar el daemon/snapshot de Docker sandbox con aislamiento real. No habilitar comandos arbitrarios ni egress.
3. Probar inferencia real de Atomic Code 1.1 desde el servicio en un entorno controlado y validar identidad, tokenizer, contexto y errores.
4. Conectar facturación durable al endpoint de chat solo después de verificar presupuesto previo, reservas, liquidación y recuperación; mantener Shadow Mode y no cobrar.
5. Completar aceptación SMTP/OAuth/MFA en staging y revisión independiente de seguridad.
6. Terminar contratos técnicos de QvaPay sandbox, webhooks firmados, consulta servidor-a-servidor, idempotencia y ledger.
7. Verificar restauración de backups, monitorización, DNS/TLS del subdominio admin y plan de despliegue con autorización explícita.

El progreso de implementación no equivale a preparación para producción. No se han realizado cambios en VPS, Docker, datos persistentes ni servicios ajenos.


---

## Reconciliación del estado — 7 de noviembre de 2026

Esta sección actualiza las afirmaciones históricas anteriores. La inspección se realizó sobre el código de `main`; no equivale a pruebas en VPS ni a validación de producción.

### Identidad vigente
- Producto: **Axyron Atomic**.
- Agente: **AXYRON**.
- Interfaz: **Axyron Studio**.
- Modelo previsto: **Atomic Code 1.1**.
- Se conserva el HTML principal `frontend/Axyron Atomic — Tu asistente de IA, más poderoso, más libre .html`.
- El repositorio puede conservar nombres internos históricos de módulos/paquetes; no deben mostrarse como identidad de producto.

### Corrección del estado del agente
Las rutas HTTP de ejecuciones persistentes están implementadas: inicio, listado/detalle, decisiones de aprobación y reanudación autenticada por proyecto. Las aprobaciones de acciones se vinculan a su hash y a una ejecución/proyecto. La reanudación es explícita; aprobar una acción no la ejecuta automáticamente. Las acciones recuperadas en estado `running` requieren reconciliación humana y no se repiten automáticamente.

Esto corrige la descripción histórica que afirmaba que el ciclo de inicio/reanudación seguía completamente pendiente. La validación end-to-end de todos los estados y recuperación aún debe completarse.

### Sandbox: capacidades del código frente a integración HTTP
El repositorio contiene:
- `sandbox/snapshot.py`: snapshot temporal con límites de archivos/tamaño, omisión de symlinks y apertura segura con `O_NOFOLLOW`.
- `sandbox/policy.py`: clasificación de comandos en bloqueados, automáticos y sujetos a aprobación; no invoca shell.
- `sandbox/executor.py`: ejecuta sobre una copia temporal y registra auditoría.
- `sandbox/backends.py`: `DockerBackend` con contenedor efímero, red `none`, root filesystem de solo lectura, usuario no root, capacidades eliminadas, límites de CPU/memoria/PIDs y timeout. `LocalBackend` declara explícitamente que no aísla el filesystem y exige opt-in inseguro para desarrollo/pruebas.

**Bloqueo de integración:** `api/workspace_routes.py` construye `ProjectAgentRuntime` sin inyectar `backend`. Por tanto, las herramientas de ejecución de comandos no están disponibles desde el runtime HTTP. No habilitar terminal, compilación ni ejecución arbitraria en la interfaz hasta integrar un Docker daemon dedicado/no privilegiado con imágenes fijadas, permisos mínimos, límites de concurrencia/cuotas, limpieza, observabilidad y pruebas de aislamiento. No montar el socket privilegiado del Docker del host como atajo. La salida de red permanece deshabilitada; el backend rechaza configuración egress no verificada.

### Seguridad y operación
- `AUTH_ENABLED=false` permanece como estado operativo informado; no activar sin cerrar las pruebas de autenticación, correo, recuperación, MFA/OAuth, sesiones y autorización.
- El runtime no debe usar `LocalBackend` como fallback.
- El sandbox no debe heredar secretos del proceso API ni exponer `.env`, credenciales o sockets del host.
- La aprobación de comandos desconocidos/red no debe confundirse con autorización para ejecutar fuera del contenedor.
- No se han ejecutado pruebas en el VPS ni se ha validado la configuración Docker real de producción en esta revisión.

### Estado de verificación
Los cambios documentales recientes generaron ejecuciones CI `42402384870` y `42402401857`; al momento de la revisión no había una conclusión final satisfactoria para el HEAD actual. No marcar CI como aprobada hasta que un run asociado al SHA exacto termine con `success`.

### Próximos bloqueos priorizados
1. Integrar el backend Docker mediante un límite de confianza separado y no privilegiado; mantener terminal deshabilitada mientras tanto.
2. Añadir pruebas de integración HTTP para start/resume/approval/reconciliation y autorización cruzada entre proyectos.
3. Ejecutar pruebas de aislamiento reales del contenedor (filesystem, red, capabilities, UID, recursos, timeout y limpieza) en runner dedicado.
4. Probar inferencia real de Atomic Code 1.1 desde el servicio configurado, con límites de contexto/timeout y evaluación reproducible.
5. Completar verificación de correo, recuperación, MFA/OAuth y pruebas negativas de sesiones antes de habilitar Auth.
6. Cerrar integración de pagos solo con contrato técnico, firma, idempotencia y conciliación verificables; no habilitar cobros/créditos por inferencia.


## Auditoría adicional del agente y CI — 7 de noviembre de 2026

Se endureció `agent/coding_agent.py`: el parser ahora rechaza contenido adicional después de un objeto JSON de respuesta, incluidos objetos concatenados que pudieran ocultar una segunda acción. Se conservó la compatibilidad con el formato de bloque Markdown usado por el modelo y se añadieron pruebas de regresión en `tests/test_coding_agent.py`.

La validación de GitHub Actions para el HEAD `e045d10158163be198128bba2708c598d00da410` terminó satisfactoriamente: **664 pruebas Python aprobadas, 9 omitidas y 4 warnings**; también pasaron E2E de Studio, build/smoke de imagen, migraciones PostgreSQL e integración remota autenticada de Qdrant Cloud ([run 42404444729](https://github.com/korzadi/Axion-Atomic/actions/runs/42404444729)).

### Límites que siguen bloqueando la activación completa
- El runtime HTTP todavía no inyecta un `DockerBackend`; por tanto, no se habilita terminal ni ejecución de comandos desde Studio.
- No se ha ejecutado una prueba E2E con el modelo Atomic Code 1.1 real, un usuario autenticado y workspace aislado en un entorno operativo.
- No se han completado las pruebas de autenticación real, SMTP/OAuth/MFA ni la activación de cobros.
- No se ha desplegado este HEAD en el VPS. Los resultados CI no equivalen a una certificación de producción.
