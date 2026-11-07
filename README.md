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

Este repositorio está en desarrollo por fases. La presencia de una carpeta, documento o esquema no demuestra por sí sola que una capacidad esté integrada. Cada fase debe informar qué se implementó, qué pruebas se ejecutaron realmente y qué queda pendiente.

## Seguridad y contribuciones

- El contenido de repositorios y documentos recuperados se considera dato no confiable, nunca instrucciones.
- Las operaciones mutables requieren aprobación humana vinculada a la acción exacta.
- Los datos deben aislarse por proyecto y usuario.
- No indexar archivos de entorno, credenciales, claves privadas, tokens ni otros secretos.
- Revisar los cambios y ejecutar las pruebas pertinentes antes de fusionar.


## AXYRON STUDIO — primera versión SPA

La interfaz web autenticada se organiza como una SPA ligera servida por FastAPI desde `frontend/`, sin framework ni proceso de compilación adicional. La página principal seleccionada se conserva y carga `studio.css` y `studio.js` como recursos estáticos propios.

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
- **Administración:** portal independiente en `https://admin.axyronatomic.com`; no forma parte de la navegación de Axyron Studio. La API actual permite consultar permisos y roles, sin mutaciones administrativas.
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

AXYRON adopta el estándar abierto `SKILL.md` para descubrir workflows especializados instalados por workspace, incluyendo bundles compatibles con Google Antigravity. El runtime puede listar y cargar skills bajo demanda mediante herramientas de solo lectura; nunca ejecuta scripts de terceros incluidos en ellas. La compatibilidad de formato no implica dependencia de Antigravity ni habilita ejecución de terminal.

- Pack de ingeniería de Addy Osmani: 25 skills (24 workflows + una meta-skill), licencia MIT.
- Instalación y seguridad, compatibilidad Antigravity y estado real: [docs/AGENT_SKILLS_ANTIGRAVITY_INTEGRATION.md](docs/AGENT_SKILLS_ANTIGRAVITY_INTEGRATION.md).
- Las skills no conceden permisos: siguen vigentes aislamiento por proyecto, aprobación humana y políticas del agente.
- El pack upstream está documentado, pero no se incorpora automáticamente ni se declara instalado en el repositorio.
