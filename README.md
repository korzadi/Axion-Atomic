# AXYRON ATOMIC

Plataforma de ingeniería de software supervisada, modular y verificable.

## Identidad oficial

- **Producto:** AXYRON ATOMIC
- **Agente principal:** AXYRON
- **Modelo principal:** ATOMIC CODE 1.1
- **Interfaz web:** AXYRON STUDIO
- **Modelo oficial:** https://huggingface.co/Korzadi/Atomic-Code-1.1

El código de este repositorio es la base técnica que se está adaptando a AXYRON ATOMIC. Los nombres históricos del proyecto de partida no forman parte de la identidad del producto.

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

## Estado de implementación

- [Matriz de aceptación y seguimiento V1.0](docs/V1_ACCEPTANCE_MATRIX.md)
- **Estado verificado (2026-11-08):** `main = fa0a536` con CI 6/6 en verde (run `42526343714`: python-tests, postgres-migrations, qdrant-cloud-integration, **qdrant-e2e**, container-image-build, studio-browser-e2e). Producción actualizada hasta `a298344` con autenticación habilitada y readiness `ready` (el delta `fa0a536` son solo documentos). Cobros, QvaPay y sandbox siguen desactivados. La actualización de producción a `fa0a536` y los cambios de esta rama corresponden al propietario. La V1.0 no se declara liberada (`REL-01` bloqueada).

Este repositorio está en desarrollo por fases. La presencia de una carpeta, documento o esquema no demuestra por sí sola que una capacidad esté integrada. Cada fase debe informar qué se implementó, qué pruebas se ejecutaron realmente y qué queda pendiente.

## Seguridad y contribuciones

- El contenido de repositorios y documentos recuperados se considera dato no confiable, nunca instrucciones.
- Las operaciones mutables requieren aprobación humana vinculada a la acción exacta.
- Los datos deben aislarse por proyecto y usuario.
- No indexar archivos de entorno, credenciales, claves privadas, tokens ni otros secretos.
- Revisar los cambios y ejecutar las pruebas pertinentes antes de fusionar.


## AXYRON STUDIO — primera versión SPA

AXYRON STUDIO se distribuye como un servicio independiente: `Dockerfile.frontend` construye la imagen Nginx sin privilegios `axyron-atomic-frontend`, mientras `Dockerfile` construye exclusivamente la API Python `axyron-atomic-api`. El frontend sirve los archivos de `frontend/` y reenvía las rutas dinámicas al servicio interno `api:8000`; el puerto local `127.0.0.1:8070` es la entrada web unificada. La página principal seleccionada se conserva y carga `studio.css` y `studio.js`.

Uso desde la perspectiva del usuario final: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

### Secciones de la primera versión

- **Resumen:** estado HTTP de la API, proyectos y consumo real disponible.
- **Proyectos:** lista y creación mediante `/auth/projects`.
- **Atomic Code:** chat autenticado mediante `/workspace/chat/history` y `/workspace/chat/completions`; no ofrece streaming porque el backend no lo implementa.
- **Conocimiento:** indexación de texto y carga de documentos, listado y eliminación de fuentes por proyecto.
- **Agente Axyron:** ejecuciones persistentes y decisiones de aprobación disponibles en el backend. La aprobación registra una decisión; no debe interpretarse como ejecución automática de la acción.
- **Modelos Atomic:** catálogo del servidor. Atomic Video, Atomic Vision y Atomic Reasoning se identifican como próximas actualizaciones mientras no estén publicados como disponibles.
- **Consumo:** telemetría por proyecto cuando existen mediciones.
- **Facturación:** catálogo y órdenes propias en modo informativo; no se inicia checkout ni se acreditan créditos desde la interfaz.
- **Cuenta y seguridad:** datos de sesión y estado/enrolamiento MFA; las operaciones no expuestas por el backend no se simulan.
- **Administración:** portal independiente en `https://admin.axyronatomic.com`; no forma parte de la navegación de Axyron Studio. La API permite consultar permisos y roles, conceder/revocar roles globales y cambiar el estado de cuentas de forma auditada con confirmaciones y MFA; los cobros y precios comerciales siguen desactivados.
- **Privacidad y legal:** controles técnicos existentes y elementos legales pendientes, sin simular solicitudes de datos que aún no tienen endpoint.
- **API e integraciones:** estado informativo de la API y conectores pendientes de un flujo seguro de credenciales.
- **Herramientas:** capacidades del runtime supervisado y sandbox/automatización identificados como próximas actualizaciones cuando el ciclo no esté validado.

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
