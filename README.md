# AXYRON ATOMIC

Plataforma de ingeniería de software supervisada, modular y verificable.

## Identidad oficial

- **Producto:** AXYRON ATOMIC
- **Agente principal:** AXYRON
- **Modelo principal:** ATOMIC CODE 1.1
- **Interfaz web:** AXYRON STUDIO
- **Modelo oficial:** https://huggingface.co/Korzadi/Atomic-Code-1.1

El código de este repositorio es la base técnica que se está adaptando a AXYRON ATOMIC. Los nombres históricos del proyecto de partida no forman parte de la identidad del producto.

## Dos aplicaciones frontend

- **Web principal** (`frontend/`): landing, páginas propias (`/modelos.html`, `/funciones.html`, …), registro, login, comercial e SSO saliente (`/sso-start`).
- **AXYRON Studio** (`studio/`): aplicación independiente con rutas reales (`/dashboard`, `/projects`, `/code`, `/knowledge`, `/agent`, `/models`, `/usage`, `/billing`, `/buy`, `/account`, `/security`, `/privacy`, `/integrations`, `/tools`). Documento, estilos raíz y navegación propios; protección de sesión; 404 propia.
- **SSO** landing ↔ Studio por código de un solo uso con sesión nueva host-only (sin ampliar el dominio de las cookies). Ver `docs/AXYRON_STUDIO_INDEPENDENT.md`.

## Arquitectura objetivo

- Axyron Core y Agent Runtime.
- Model Manager y Model Router, con ATOMIC CODE 1.1 como modelo principal.
- AXYRON STUDIO como interfaz web propia.
- Analizador de repositorios y herramientas de ingeniería.
- RAG y memoria aislados por proyecto.
- Aprobaciones humanas, auditoría e idempotencia.
- Sandbox de ejecución con políticas y límites.
- API propia y compatibilidad OpenAI.
- PostgreSQL y Qdrant.
- Payment Manager intercambiable con integración QvaPay.
- Privacidad, accesibilidad, documentación legal y controles de protección al consumidor.
- Preparación de entrenamiento y evaluación en GPU externa bajo demanda.

## Límites operativos

- No depende de Open WebUI ni de otra interfaz externa.
- Ollama, cuando sea compatible con el modelo, se consume como servicio externo ya existente. No se instala, reemplaza ni modifica desde este proyecto.
- No se entrena en el VPS.
- No se conecta ni despliega sobre el VPS desde este repositorio.
- No se construyen imágenes Docker, ejecutan migraciones ni reinician servicios sin autorización expresa.
- Los secretos nunca deben incorporarse al repositorio ni exponerse en logs.

## Workspaces y aislamiento por proyecto

- La creación web de proyectos provisiona un directorio hijo exclusivo bajo `WORKSPACE_ROOT` (por defecto `/workspace`) y aplica permisos `0700`.
- La resolución del workspace rechaza enlaces simbólicos, rutas fuera de la raíz y directorios con permisos de grupo u otros; no corrige permisos de directorios existentes automáticamente.
- En Compose, `./workspace` se monta en `/workspace` y la API se ejecuta como UID `10001` (`appuser`). Por ello, el directorio del host debe existir y ser escribible por ese UID antes de habilitar la creación de proyectos. No se cambia su propietario ni se ejecutan `chown` automáticamente.
- Si la raíz no está disponible o no permite escritura, la creación falla de forma cerrada; no se crea una raíz alternativa.

## Plan comercial: tokens, créditos y rentabilidad

El alcance de medición de tokens, cuotas, costes por modelo, créditos, suscripciones, infraestructura, administración y rentabilidad está incorporado al roadmap del proyecto. Sus valores comerciales son propuestas configurables, no planes activos ni costes reales verificados.

- [Auditoría, diseño y roadmap de tokens, créditos y economía](docs/COMMERCIAL_TOKENS_CREDITS_ECONOMICS_ROADMAP.md)
- [Diseño técnico de facturación y créditos](docs/COMMERCIAL_BILLING_TECHNICAL_DESIGN.md)
- [Implementación de medición Shadow Mode](docs/SHADOW_USAGE_IMPLEMENTATION.md)
- [Diseño e implementación de persistencia PostgreSQL para Shadow Mode](docs/SHADOW_USAGE_POSTGRESQL_DESIGN.md)
- [Puerta de salida a producción inicial](docs/PRODUCTION_INITIAL_RELEASE_GATE.md)
- La Fase 1 contiene la auditoría inicial de los módulos inspeccionados y las brechas verificadas.
- No habilitar cobros, ventas ni límites comerciales hasta completar las fases de diseño, implementación, seguridad y pruebas.

## Estado de implementación (reconciliado 2026-11-09)

- [Matriz de aceptación V1.0](docs/V1_ACCEPTANCE_MATRIX.md) · [Progreso](docs/V1_PROGRESS.md) · [Puerta producción](docs/PRODUCTION_INITIAL_RELEASE_GATE.md)
- **HEAD `main`: `4134313` (merge PR #25) — CI 6/6** (run `42607072336`: python-tests, studio-browser-e2e, container-image-build, postgres-migrations 001–025, qdrant-e2e, qdrant-cloud-integration). Suite local: 1072 passed/27 skipped.
- **Implementado y desplegado (controlado, autorizado):** Studio independiente + SSO, auth/MFA/privacidad, agente/RAG, facturación ledger, admin, migraciones al día (025). Legales publicados (`/privacidad.html /terminos.html /reembolsos.html`). QvaPay activo (catálogo 4 planes, `checkout_enabled:true`, token en `.env` sin exponer). AGT-04 **verificada en runtime** (aislamiento PASÓ). `/health` 6/6.
- **No liberada comercialmente.** Pendiente externo (evidencia real): (1) primer pago QvaPay E2E, (2) E2E buzón/MFA/OAuth/SSO con cuentas reales, (3) smoke autenticado final + aceptación formal. No se simulan verificaciones ni se movieron fondos.

## Seguridad y contribuciones

- El contenido de repositorios y documentos recuperados se considera dato no confiable, nunca instrucciones.
- Las operaciones mutables requieren aprobación humana vinculada a la acción exacta.
- Los datos deben aislarse por proyecto y usuario.
- No indexar archivos de entorno, credenciales, claves privadas, tokens ni otros secretos.
- Revisar los cambios y ejecutar las pruebas pertinentes antes de fusionar.


## AXYRON STUDIO — aplicación independiente

AXYRON STUDIO se distribuye como un servicio independiente: `Dockerfile.frontend` construye la imagen Nginx sin privilegios `axyron-atomic-frontend`, mientras `Dockerfile` construye exclusivamente la API Python `axyron-atomic-api`. Nginx sirve la web principal desde `frontend/` y el Studio desde `studio/` (documento, estilos y router propios); el puerto local `127.0.0.1:8070` es la entrada web unificada y ambos frontends consumen la misma API `api:8000`.

Uso desde la perspectiva del usuario final: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

### Secciones de aplicación

- **Resumen:** readiness real (incluye estado degradado con sus dependencias), proyectos, última ejecución del agente y disponibilidad de modelos.
- **Proyectos:** lista, creación, selección y apertura mediante `/auth/projects`; no se simula borrado porque el backend no expone `DELETE`.
- **Atomic Code:** chat autenticado mediante `/workspace/chat/history` y `/workspace/chat/completions`, con historial completo, idempotencia por payload y streaming SSE real (`stream=true`, `text/event-stream`) preservando el contrato JSON no-stream; la facturación/liquidación usa medición verificable (fail-closed) antes de confirmar cobros.
- **Conocimiento:** indexación de texto y carga de documentos, listado y eliminación de fuentes por proyecto.
- **Agente Axyron:** ejecuciones persistentes, detalle, aprobaciones de acción y de plan, `resume`, `cancel` y `reconcile`. La aprobación registra una decisión; no debe interpretarse como ejecución automática de la acción.
- **Modelos Atomic:** catálogo del servidor y verificación en vivo con `/workspace/models/availability`. Atomic Video, Atomic Vision y Atomic Reasoning se identifican como próximas actualizaciones mientras no estén publicados como disponibles.
- **Consumo:** telemetría por proyecto cuando existen mediciones.
- **Facturación:** catálogo real, órdenes propias y checkout QvaPay Lightning; la acreditación depende de la conciliación idempotente del servidor, nunca del navegador.
- **Cuenta y seguridad:** datos de sesión y estado/enrolamiento MFA. El logout revoca solo la sesión del host Studio; no existe logout global ni cambio de contraseña con sesión activa, y no se simulan.
- **Administración:** portal independiente en `https://admin.axyronatomic.com`; no forma parte de la navegación de Axyron Studio. La API permite consultar permisos y roles, conceder/revocar roles globales y cambiar el estado de cuentas de forma auditada con confirmaciones y MFA. La facturación y los cobros dependen de los flags del servidor y de la conciliación idempotente; el primer pago real E2E sigue pendiente.
- **Privacidad y legal:** controles técnicos existentes y elementos legales pendientes, sin simular solicitudes de datos que aún no tienen endpoint.
- **API e integraciones:** estado informativo de la API y conectores pendientes de un flujo seguro de credenciales.
- **Herramientas:** capacidades del runtime supervisado y sandbox/automatización identificados como próximas actualizaciones cuando el ciclo no esté validado.

### Pruebas y límites de la aplicación Studio

- `python -m pytest -q` cubre contratos backend y estáticos (incluido `tests/test_studio_app_contract.py`); `node tests/e2e/studio-app-browser.mjs` ejecuta el E2E con Playwright sobre backend simulado; `python scripts/check_frontend_js.py` valida la sintaxis de los scripts.
- El E2E con dependencias reales (Ollama, Qdrant, PostgreSQL, dominios y TLS) y el CI del SHA final siguen pendientes. El SSO requiere `STUDIO_ORIGIN` y no existe cierre de sesión global.

### Identidad visual

La experiencia usa una paleta futurista oscura azul profundo, cian eléctrico, azul y violeta, paneles translúcidos, estados explícitos y navegación responsive. El tema claro permanece disponible como preferencia del usuario.

### Ecosistema extensible — roadmap de próximas actualizaciones

AXYRON STUDIO contempla una capa de extensibilidad para conectar AXYRON con servicios y herramientas externas. **Estas capacidades forman parte del roadmap; no se consideran disponibles hasta que exista implementación de backend, controles de seguridad y pruebas verificadas.**

- **AXYRON CONNECT:** centro de conexiones para vincular aplicaciones y servicios externos, por ejemplo plataformas de desarrollo, almacenamiento, comunicación y servicios cloud.
- **App Connectors:** conectores autenticados mediante OAuth u otros mecanismos apropiados, con permisos mínimos, autorización explícita, renovación y revocación de credenciales.
- **Plugin Hub:** catálogo de plugins de terceros y propios, con procedencia, firma o verificación, versión, permisos declarados y ciclo de actualización.
- **Skill Library:** biblioteca de skills que amplíen las capacidades del agente mediante instrucciones y flujos especializados, con revisión de contenido y límites de uso.
- **Tool Registry:** registro de herramientas invocables por AXYRON, con esquemas de entrada/salida, validación, permisos por proyecto y aprobación humana para acciones sensibles.
- **Protocolos y APIs:** evaluación de compatibilidad con MCP, APIs HTTP y webhooks; cada transporte deberá aplicar autenticación, autorización, límites y validación de entradas.
- **Automation Hub:** flujos y automatizaciones programadas, condicionados a controles de ejecución, auditoría, cuotas, cancelación y recuperación segura.
- **Security Center:** vista de conexiones activas, permisos concedidos, actividad, auditoría y desconexión/revocación.

**Estado actual:** la SPA presenta estos módulos como **Próxima actualización**. No existe todavía un catálogo operativo de plugins/skills, instalador de extensiones, gestor universal de conectores ni autorización automática de herramientas. No anunciar ni simular esas funciones como disponibles.

**Criterios mínimos antes de habilitar una extensión:** identidad y procedencia verificables; permisos mínimos y aislados por usuario/proyecto; secretos almacenados fuera del repositorio y protegidos; validación de entradas y salidas; límites de recursos y red; aprobación explícita para operaciones sensibles; registro auditable; revocación y desinstalación seguras; pruebas de aislamiento y compatibilidad.

La SPA usa únicamente rutas ya existentes en el backend. Las capacidades no implementadas se muestran como **Próxima actualización** o como operaciones deshabilitadas. Esta interfaz no habilita por sí sola autenticación, pagos, servicios ni despliegue en producción.


## AXYRON Agent Skills y Google Antigravity

AXYRON adopta el estándar abierto `SKILL.md` para descubrir workflows especializados del proyecto y skills confiables empaquetadas con la aplicación, incluyendo bundles compatibles con Google Antigravity. El runtime puede listar y cargar skills bajo demanda mediante herramientas de solo lectura; nunca ejecuta scripts de terceros incluidos en ellas. La compatibilidad de formato no implica dependencia de Antigravity ni habilita ejecución de terminal.

- Pack de ingeniería de Addy Osmani: 25 skills (24 workflows + una meta-skill), licencia MIT.
- Instalación fijada y verificada mediante `bash scripts/install_agent_skills.sh`; instrucciones y seguridad: [docs/AGENT_SKILLS_ANTIGRAVITY_INTEGRATION.md](docs/AGENT_SKILLS_ANTIGRAVITY_INTEGRATION.md).
- Las skills no conceden permisos: siguen vigentes aislamiento por proyecto, aprobación humana y políticas del agente.
- El pack upstream está documentado, pero no se incorpora automáticamente ni se declara instalado en el repositorio.


## Skills especializadas de AXYRON

Las skills versionadas dentro de `.agents/skills/` se empaquetan en la imagen de la API y se descubren automáticamente desde los workspaces aislados mediante el registro Agent Skills. También se pueden añadir skills locales por proyecto:

- **Gravity UI** (`.agents/skills/gravity-ui/`): guía técnica para el ecosistema React `@gravity-ui/*`; ayuda a elegir paquetes, consultar APIs según la versión instalada, aplicar temas y evitar componentes o propiedades inventados. No instala dependencias ni convierte Gravity UI en el diseño obligatorio de Axyron Studio.
- **Codebase Summary** (`.agents/skills/codebase-summary/`): análisis general del repositorio en tres fases (explorar, sintetizar y validar). Genera y mantiene el contexto persistente en `.agents/project-context/SUMMARY.md` y `.agents/project-context/summary.json`, con arquitectura, tecnologías, módulos, flujos, interfaces/API, configuración y brechas verificadas.

Para generar el mapa inicial del proyecto, solicita a AXYRON: **«Usa la skill codebase-summary para analizar todo este repositorio y guardar/actualizar el contexto del proyecto»**. Para refrescarlo tras cambios importantes, vuelve a solicitar el análisis. AXYRON debe leer el resumen al comenzar trabajos de ingeniería, contrastarlo con el código vigente y nunca tratarlo como sustituto de la fuente.

- **Agent Skills** (`.agents/skills/agent-skills/`): creación, validación, organización y mantenimiento seguro de skills compatibles con el estándar abierto.

El conjunto versionado contiene **20 skills**: 17 de ingeniería, Gravity UI, Codebase Summary y Agent Skills. Las skills globales se leen desde la raíz confiable de la aplicación; no se copian a las carpetas de los usuarios.

Estas skills son guías; durante el análisis de código, Codebase Summary es de solo lectura; no habilitan ejecución de scripts de terceros, instalaciones, despliegues ni acciones fuera de las aprobaciones existentes. No deben incluir secretos ni valores de variables de entorno en los informes.


## AXYRON Engineering Skills — programación integral

El agente incorpora un conjunto de skills especializadas para acompañar el ciclo completo de desarrollo. Se descubren desde `.agents/skills/` y se cargan bajo demanda; AXYRON no necesita leerlas todas para cada tarea.

**Flujo principal:** `programming-workflow`, `feature-design`, `implementation-planning`, `architecture-design`.

**Construcción:** `python-backend`, `frontend-web`, `api-contracts`, `postgresql-database`.

**Calidad:** `test-engineering`, `systematic-debugging`, `code-review`, `receiving-code-review`, `performance-engineering`.

**Seguridad y mantenimiento:** `secure-coding`, `git-workflow`, `technical-documentation`, `accessibility-ux`.

Las skills son guías de trabajo, no plugins ejecutables. El agente debe consultar `programming-workflow` antes de tareas de programación y cargar solo las especializadas que correspondan. Se mantienen las aprobaciones humanas, el aislamiento por proyecto y las restricciones operativas existentes. Ninguna skill autoriza despliegues, cambios en producción, operaciones destructivas, ejecución de scripts de terceros ni acceso a secretos.

### Estándares de ingeniería

- Inspeccionar el código y las instrucciones del repositorio antes de modificar.
- Mantener sincronizados backend, frontend, contratos, pruebas y documentación.
- No inventar endpoints, datos demo ni capacidades aún no implementadas.
- Investigar la causa raíz antes de corregir errores.
- Probar los cambios y verificar el resultado antes de declarar que están terminados.
- Revisar seguridad, permisos, aislamiento, accesibilidad y regresiones.
- Documentar límites y evidencias reales, sin afirmar pruebas o despliegues no realizados.


### Activación automática de Agent Skills

El runtime carga automáticamente `programming-workflow` al iniciar cada ejecución del agente y selecciona skills adicionales según el tema de la solicitud. La selección normaliza acentos y reconoce términos técnicos en español e inglés (por ejemplo Python/FastAPI, frontend, APIs, PostgreSQL, pruebas, depuración, seguridad o Git). La selección es una ayuda contextual: AXYRON debe comprobar que la skill existe, leer su contenido mediante `read_skill` y contrastarlo con el repositorio. Si una skill no está instalada, continúa sin inventarla. Las skills no otorgan permisos ni sustituyen aprobaciones.

**Herramientas de ingeniería actualmente expuestas:** lectura y búsqueda de archivos, listado de directorios, resumen estructural del repositorio, estado/diff/log Git, propuestas de creación/edición/eliminación y propuestas de commit/rama. Las herramientas de terminal y ejecución de pruebas solo se exponen cuando el runtime recibe un backend Docker aislado y configurado con imágenes fijadas por digest. La API puede inyectarlo solo con `SANDBOX_DOCKER_ENABLED=true` y un daemon dedicado; la configuración está desactivada por defecto y no se ha validado end-to-end, por lo que no debe anunciarse terminal ni ejecución automática de pruebas como disponible en Studio.


## Instalación en VPS

El repositorio incluye un instalador por etapas y conservador para levantar los servicios definidos en Docker Compose:

- Guía: [docs/VPS_INSTALLATION.md](docs/VPS_INSTALLATION.md).
- Preparación privada, sin desplegar: `sudo bash scripts/install_vps.sh --prepare`.
- Validación previa: `sudo bash scripts/install_vps.sh --check`.
- Despliegue explícito, con confirmación y respaldo PostgreSQL antes de migraciones: `sudo bash scripts/install_vps.sh --deploy`.

El instalador no modifica servicios existentes, Nginx, UFW, Ollama ni KorzadiVPN; si detecta el proyecto existente, cualquiera de los volúmenes PostgreSQL legado/actual o puertos ocupados, se detiene para evitar una segunda base de datos. No realiza despliegues automáticamente desde GitHub Actions.

La conectividad privada API→Ollama se diagnostica y configura aparte con `scripts/configure_ollama_firewall.sh --check` / `--apply`; detecta la subred e interfaz bridge reales y limita UFW a esa red, IP privada y puerto 11434. No modifica `OLLAMA_HOST`, no expone Ollama en `eth0` y no toca KorzadiVPN. Detalles y confirmación: [docs/VPS_INSTALLATION.md](docs/VPS_INSTALLATION.md#conexión-privada-con-ollama).


## Contexto seguro de construcción Docker

El archivo `.dockerignore` excluye secretos, archivos de entorno reales, workspaces, conocimiento privado, backups, bases de datos locales y metadatos Git del contexto de construcción. Mantiene disponibles las fuentes de la aplicación y las skills versionadas que el Dockerfile empaqueta. No añadas credenciales ni datos de usuarios al contexto de build.


Para inventariar los recursos Axyron ya existentes en el VPS sin modificar servicios, ejecuta `bash scripts/inspect_vps_state.sh`. El informe omite valores de `.env` y se limita a contenedores/redes Axyron, el volumen persistente y los puertos de la aplicación.
