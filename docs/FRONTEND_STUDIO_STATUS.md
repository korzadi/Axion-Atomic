# Estado de AXYRON STUDIO — frontend web

**Rama:** `main`  
**Estado:** interfaz web integrada con FastAPI y conectada a varios endpoints reales autenticados. Esta situación no equivale a un SaaS listo para producción ni a un despliegue validado.

## Experiencia pública y acceso

- Página pública responsive con identidad AXION ATOMIC.
- Registro por correo y contraseña con aceptación de términos.
- Inicio y cierre de sesión con cookie HttpOnly y protección CSRF.
- Verificación de correo y recuperación de contraseña mediante tokens.
- Límites antiabuso para registro, login, OAuth y recuperación; su comportamiento en producción depende de configuración y persistencia PostgreSQL.
- OAuth Google y GitHub dispone de rutas de inicio/callback y validación de identidad. La operación real requiere credenciales externas, URLs de callback correctas y pruebas con cuentas de proveedor; no se considera validada solo por mostrar los botones.
- Las rutas de autenticación permanecen sujetas a `AUTH_ENABLED`; no se habilitó esa variable ni se modificó configuración del VPS.

## AXION STUDIO

### Panel de inicio

- Al validar la sesión, el usuario llega a un panel con saludo y resumen.
- El panel consulta `GET /auth/projects` y muestra el número y los cinco proyectos recientes de la cuenta.
- Consulta `GET /billing/catalog` para mostrar modelos publicados y el estado de checkout que informa el servidor.
- No presenta saldos, inferencias activas ni disponibilidad del runtime sin una API que lo confirme.
- Los accesos rápidos navegan a Chat IA, Proyectos y Modelos.

### Módulos conectados

- **Proyectos:** `GET /auth/projects` y `POST /auth/projects`; la creación asigna la membresía `owner` en el backend.
- **Chat IA:** `POST /workspace/chat/completions` y `GET /workspace/chat/history`; carga proyectos autorizados, envía sesión y CSRF y persiste el historial en PostgreSQL por usuario y proyecto (límite de 100 mensajes). El backend recupera contexto RAG filtrado por proyecto y usa el modelo configurado. No implementa streaming ni ejecución de herramientas. El contexto recuperado se serializa como dato JSON no confiable en el mensaje de sistema y hay una prueba contra instrucciones hostiles dentro de documentos; esto reduce el riesgo de inyección, pero no sustituye evaluaciones adversariales con el modelo real.
- **Agentes / aprobaciones:** consulta historial y detalle de ejecuciones y permite registrar decisiones de aprobación según rol de proyecto. Aprobar no ejecuta ni reanuda herramientas; la integración end-to-end del runtime sigue pendiente.
- **Modelos:** consulta `GET /billing/catalog`. El catálogo actual es informativo y no habilita checkout ni facturación.
- **Pagos:** consulta órdenes propias e historial mediante `GET /billing/orders` y `GET /billing/orders/{id}`. No crea órdenes, confirma pagos ni acredita créditos.
- **Administración:** consulta permisos globales con `GET /admin/access/me`; no concede roles ni permite mutaciones.

### Módulos todavía informativos o incompletos

- Atomic Video: investigación y desarrollo; no hay flujo de generación audiovisual de producción conectado.
- Atomic Vision y Atomic Reasoning: no se deben presentar como servicios disponibles sin verificación de sus runtimes.
- Conocimiento: interfaz conectada para indexar texto y cargar PDF/DOCX/TXT/Markdown (máximo 5 MB y 100000 caracteres extraídos), listar fuentes por proyecto, reindexar fuentes administrables y eliminarlas. La carga usa CSRF, valida rol y limita solicitudes; la recuperación RAG del chat queda filtrada por proyecto. No hay OCR: los PDF escaneados sin texto extraíble se rechazan. Hay pruebas de navegador para los flujos de interfaz (login, carga, refresco y permisos), pero sus endpoints se simulan en el navegador. También hay una prueba de integración que ejecuta la ruta de carga, la extracción TXT real y el ciclo de indexación/listado/recuperación sobre un doble de prueba del protocolo Qdrant; embeddings se sustituyen por un vector determinista. Las pruebas no arrancan un servidor ni almacenan datos localmente. La configuración de ejecución usa Qdrant Cloud mediante URL HTTPS y API key; la conexión real debe verificarse con credenciales del clúster del operador.
- Atomic Code como módulo independiente: el modelo se utiliza desde Chat IA; faltan controles y experiencia especializada de programación dentro del workspace.
- Administración: la API disponible es de solo lectura; faltan operaciones administrativas seguras, auditadas y probadas.
- Agente ejecutor: inicio y reanudación HTTP persistentes están implementados; la recuperación de acciones interrumpidas requiere reconciliación humana y no se repite automáticamente. El sandbox Docker y la ejecución de comandos siguen pendientes.

## Límites de producción

- No se ha validado OAuth con credenciales reales ni se ha probado el ciclo completo de correo en un dominio de producción.
- No se ha habilitado autenticación en el VPS.
- El chat no soporta streaming y no debe confundirse con un agente que ejecuta código o modifica archivos.
- El sistema de facturación permanece en modo no conectado al endpoint real de chat; no se deben activar cobros hasta completar idempotencia HTTP, proveedor KMS real, attestation verificable del runtime y pruebas end-to-end.
- QvaPay requiere confirmar el mecanismo de referencia de orden y verificación server-to-server/webhook firmado antes de aceptar pagos reales.
- La imagen Docker y el despliegue en VPS requieren una validación separada y aprobación expresa del operador.

## Siguientes bloques

1. Mantener CI verde y ampliar la integración del ciclo de fuentes con pruebas de servicios de prueba; la carga TXT, extracción, indexación, listado y recuperación ya tienen cobertura integrada sobre un doble del protocolo Qdrant para validar el ciclo sin almacenamiento local. La conexión real de ejecución se dirige a Qdrant Cloud; la aceptación remota queda pendiente de disponer de URL y API key de un clúster de pruebas. OCR de PDF escaneados queda como mejora posterior al MVP.
2. Completar el runtime persistente del agente y su ciclo de aprobación/reanudación.
3. Completar la experiencia de Atomic Code y el módulo de conocimiento usando únicamente endpoints reales.
4. Validar OAuth, correo y configuración de autenticación en un entorno de pruebas.
5. Completar los gates de facturación y pagos sin habilitar cobros prematuramente.
6. Validar build e instalación en un entorno autorizado antes de cualquier despliegue.


## Validación CI — 6 de noviembre de 2026

La ejecución de GitHub Actions del commit `94b1d864c20db560af5007b77c3cb85e380bf791` terminó con resultado **success** (run [42291872701](https://github.com/korzadi/Axion-Atomic/actions/runs/42291872701)):

- Python: **592 passed, 8 skipped**, 3 warnings.
- AXION STUDIO browser E2E: **3 escenarios aprobados**.
- PostgreSQL: migraciones aplicadas, idempotencia verificada y comprobaciones de esquema/transacciones aprobadas.
- Esta CI usa un doble del protocolo Qdrant para pruebas automatizadas; **no demuestra conectividad con el clúster remoto real**.
- La conexión Qdrant Cloud, autenticación OAuth con proveedores reales y despliegue empaquetado siguen pendientes de validación en entorno de pruebas autorizado.


## Estado operativo

Los cambios de código se guardan en el repositorio. No se ha accedido al VPS, construido o reiniciado Docker, aplicado migraciones, cambiado variables de entorno, alterado servicios ni modificado datos.


## Actualización de validación — 6 de noviembre de 2026 (run 42295136956)

Esta sección sustituye los estados de CI y Qdrant Cloud descritos en las secciones anteriores cuando exista contradicción:

- GitHub Actions: **success** en el commit `7fe150e3` ([run 42295136956](https://github.com/korzadi/Axion-Atomic/actions/runs/42295136956)).
- Python: **599 passed, 8 skipped**, 3 warnings.
- AXION STUDIO browser E2E: **3 escenarios aprobados**.
- PostgreSQL: job de migraciones completado con éxito.
- Qdrant Cloud remoto: **prueba autenticada aprobada**. El job creó una colección temporal, insertó vectores, buscó por proyecto, verificó aislamiento entre proyectos, eliminó puntos y eliminó su propia colección temporal. No se usó Qdrant local ni se tocaron colecciones ajenas.
- Esta prueba acredita el ciclo remoto específico del smoke test; no valida todavía reindexación completa de documentos, OAuth con proveedores reales, correo en dominio de producción, runtime de agente, cobros ni despliegue.

No se accedió al VPS ni se modificó infraestructura, servicios o datos de producción.


## Actualización — 7 de noviembre de 2026: Axyron Studio SPA

Se incorporó una primera estructura SPA ligera dentro de la aplicación FastAPI, respetando la página HTML principal seleccionada y sin añadir un framework ni un paso de build frontend. Los recursos `/studio.css` y `/studio.js` se sirven desde el directorio estático existente.

### Interfaz añadida

- Navegación integrada: Resumen, Proyectos, Atomic Code, Conocimiento, Agente Axyron, Modelos Atomic, Consumo, Facturación, Cuenta y seguridad ; la administración se mantiene fuera de la SPA, en `https://admin.axyronatomic.com`.
- Sistema visual futurista responsive con base oscura azul profundo, cian, azul y violeta; el tema claro se conserva como opción.
- Atomic Code reutiliza el módulo de chat existente y sus endpoints autenticados.
- Proyectos usa la API real de listado y creación.
- Conocimiento usa las rutas reales de ingestión, carga, listado y eliminación de fuentes.
- Agente usa las rutas de ejecución persistente, lectura de ejecuciones y aprobaciones. La UI advierte que una aprobación no ejecuta por sí sola la acción.
- Modelos consulta el catálogo público; los modelos no disponibles se etiquetan como próximas actualizaciones.
- Consumo consulta métricas reales por proyecto.
- Facturación consulta catálogo y órdenes propias; checkout permanece deshabilitado si así lo informa el backend.
- Cuenta muestra sesión y MFA; Administración muestra permisos de solo lectura y no inventa mutaciones.

### Validación añadida

- El script de CI ahora ejecuta `node --check` también sobre `frontend/studio.js`.
- La prueba de navegador sirve los nuevos recursos CSS/JS y verifica el shell SPA y su estado anónimo.
- Se añadió `tests/test_frontend_studio_spa.py` para comprobar contratos de integración con las rutas existentes.

### Límites todavía vigentes

- No se ejecutaron estas pruebas en este cambio; se espera el resultado de GitHub Actions.
- No se ha validado el aspecto visual en navegador real con una sesión autenticada.
- La autenticación del VPS permanece deshabilitada hasta completar sus gates.
- No se habilitaron cobros, operaciones administrativas mutables, ni modelos Atomic aún no disponibles.
- No se desplegó ni reinició el VPS y no se modificaron datos, volúmenes o servicios.


### Ampliación de navegación SPA

Se añadieron además las secciones **Privacidad y legal**, **API e integraciones** y **Herramientas**. Presentan los controles técnicos que sí existen y marcan como próximas actualizaciones los portales de derechos/gestión de claves, conectores y sandbox visual que todavía no tienen un flujo completo en el backend. No se inventan endpoints ni operaciones.


## Separación del portal administrativo — 7 de noviembre de 2026

Por decisión de producto, Axyron Studio mantiene todas las páginas de usuario en una sola SPA, pero excluye Administración de su navegación. El host exacto `admin.axyronatomic.com` sirve un portal independiente desde `frontend/admin.html`, con JavaScript propio, inicio de sesión en ese subdominio y lectura de `/admin/access/me`. La cookie de sesión es host-only: el administrador inicia sesión directamente en el subdominio administrativo, sin ampliar cookies al dominio padre.

El portal muestra únicamente autorización, roles y permisos reales. La API actual declara `mutations_enabled=false`; no se simulan operaciones de escritura. Para publicar el subdominio aún se requiere DNS correcto, un virtual host Nginx que proxyee a la API y certificado TLS válido. Este cambio no altera Nginx ni despliega el VPS.


## Tablero de fases — corte del 7 de noviembre de 2026

Porcentajes estimados de implementación, no porcentajes de certificación ni de disponibilidad productiva:

| Fase | Alcance | Avance estimado | Bloqueo principal |
|---|---|---:|---|
| 1 | Marca, dominio principal y landing | 95% | Validación de la versión desplegada actualizada |
| 2 | API, base de datos y servicios | 85% | Validación operativa completa tras el último cambio |
| 3 | Axyron Studio SPA y diseño unificado | 85% | Pruebas visuales autenticadas y responsive |
| 4 | Integración de páginas con API real | 75% | Recorrido completo con sesión real |
| 5 | Atomic Code y workspace | 70% | Prueba real de inferencia y persistencia con usuario autenticado |
| 6 | Registro, login, OAuth y sesiones | 55% | AUTH_ENABLED continúa desactivado; falta validar proveedores/correo reales |
| 7 | MFA y recuperación | 55% | Cerrar validación de rotación de clave y flujos reales |
| 8 | Portal admin independiente | 35% | Configurar DNS, Nginx/TLS y validar roles con cuenta autorizada |
| 9 | Facturación y pagos | 20% | Checkout, proveedor y conciliación firmada no habilitados |
| 10 | Atomic Vision, Reasoning y Video | 10% | Runtimes y productos no publicados |
| 11 | CI, pruebas y empaquetado | 75% | La última ejecución está en cola; corregidos dos fallos detectados en pruebas previas |
| 12 | Despliegue de la versión actual | 65% | Actualizar VPS requiere aprobación y procedimiento de despliegue separado |
| 13 | Auditoría final y lanzamiento público | 0% | Depende del cierre de los gates anteriores |

El portal administrativo está separado de la SPA principal y su URL prevista es `https://admin.axyronatomic.com`. El frontend del portal y el enrutamiento por Host ya están en GitHub; el DNS, Nginx y certificado de ese subdominio todavía no se han comprobado ni modificado.

La autenticación sigue desactivada en producción. No se deben aceptar registros ni presentar el portal como operativo hasta completar la validación de MFA, correo, OAuth, cookies y autorización administrativa. No se ha desplegado este corte en el VPS.


## Validación CI completada — 7 de noviembre de 2026

La ejecución GitHub Actions `42398454717` sobre el commit `9d3895081fbc20571aa790f0d804d3f4ebfde850` terminó con resultado **success**. Pasaron los trabajos de pruebas Python, navegador Playwright de Axyron Studio, build y smoke test de la imagen, migraciones PostgreSQL e integración Qdrant Cloud. El build y smoke test ocurrieron dentro de GitHub Actions; no desplegaron ni modificaron el VPS de producción.

Durante esta validación se corrigió una regla de presentación que hacía visible un enlace marcado como oculto, y el E2E se ajustó para seleccionar botones de registro/login realmente visibles. La validación CI no habilita autenticación productiva ni demuestra que el subdominio administrativo esté configurado en DNS/Nginx.

### Avance revisado tras CI

| Fase | Área | Avance estimado |
|---|---|---:|
| 1 | Marca, dominio y landing | 95% |
| 2 | API, base de datos e infraestructura | 85% |
| 3 | Axyron Studio SPA y navegación | 90% |
| 4 | Integración frontend/API | 78% |
| 5 | Atomic Code y workspace | 72% |
| 6 | Registro, login y OAuth | 55% |
| 7 | MFA, SMTP y recuperación | 55% |
| 8 | Portal administrativo independiente | 38% |
| 9 | Facturación y pagos | 20% |
| 10 | Atomic Vision, Reasoning y Video | 10% |
| 11 | CI y pruebas automatizadas | 100% |
| 12 | Despliegue de la versión actual | 65% |
| 13 | Auditoría final y lanzamiento | 0% |

Los porcentajes son estimaciones de implementación, no certificaciones de seguridad ni disponibilidad pública. El promedio simple de estas fases es aproximadamente 58%; no sustituye un criterio de salida a producción.


## Continuación autónoma V1.0 — corte técnico del 7 de noviembre de 2026

### Seguridad de sesión: corrección verificada

La revisión de `api/auth_routes.py` encontró que la cookie de sesión emitida tras login con contraseña no declaraba `HttpOnly`, aunque los flujos OAuth y MFA sí lo hacían. Se corrigió el atributo a `httponly=True` y se añadió una regresión en `tests/test_auth_routes.py` que inspecciona la cookie emitida. La cookie CSRF continúa siendo legible por JavaScript de forma intencional; la cookie de sesión no.

También quedaron implementados y probados en el corte anterior los siguientes controles de interfaz: el portal administrativo distingue sesión válida de rol administrativo global, mantiene la opción de cerrar sesión cuando la cuenta no tiene permisos y las aprobaciones del agente solo se muestran a propietarios/administradores del proyecto. El backend sigue siendo la autoridad y vuelve a comprobar esos permisos al recibir cada decisión.

### Validación automatizada del corte

GitHub Actions `42399587370`, commit `5f82e01dba972309e8ae15e6c6b7ee5afd6b76de`, terminó en **success**. Los cinco trabajos terminaron correctamente: `python-tests`, `studio-browser-e2e`, `container-image-build`, `postgres-migrations` y `qdrant-cloud-integration`. La imagen solo se construyó en CI; no hubo despliegue ni cambios en el VPS.

### Progreso por las nueve fases obligatorias

Estimaciones de implementación basadas en código inspeccionado, pruebas disponibles y bloqueos de producción documentados. No son certificación ni disponibilidad pública.

| Fase | Avance estimado | Evidencia / bloqueo principal |
|---|---:|---|
| 1. Auditoría y arquitectura | 85% | Arquitectura, rutas, gates y roadmap documentados; falta auditoría independiente completa |
| 2. Backend | 78% | API, auth, proyectos, chat, RAG y agente; faltan flujos comerciales y algunas operaciones de cuenta |
| 3. Frontend | 88% | SPA y portal admin conectados a rutas reales; faltan aceptación visual y recorrido completo con cuenta real |
| 4. Inteligencia artificial | 70% | Ollama, chat, RAG y runtime supervisado implementados; falta verificación de runtime/modelo con cuenta en entorno de staging |
| 5. Seguridad | 65% | CSRF, sesiones, rate limits, MFA, OAuth y RBAC cubiertos por pruebas; faltan rotación de claves en staging, revisión externa y pruebas de abuso |
| 6. Base de datos e infraestructura | 80% | Migraciones PostgreSQL y Qdrant Cloud validadas en CI; falta prueba de restauración y aceptación de infraestructura desplegada |
| 7. Integraciones | 55% | SMTP/OAuth implementados; falta entrega real y callback de proveedores; QvaPay requiere integración de órdenes/webhook/conciliación |
| 8. Pruebas y calidad | 85% | Cinco trabajos CI aprobados; falta carga, pruebas de recuperación y aceptación E2E de proveedores reales |
| 9. Lanzamiento V1.0 | 30% | Documentación y build CI; falta staging, gates comerciales/seguridad, despliegue aprobado y smoke test productivo |

**Promedio simple de las nueve fases: 70.7% (71%).** La cifra no significa que V1.0 esté lista: las fases de lanzamiento, integraciones reales y seguridad operativa siguen bloqueadas.

### Siguientes tareas técnicas

1. Completar pruebas de sesión y MFA para flujos de login normal, OAuth y administrador, incluyendo cookies, no-store y revocación.
2. Verificar el recorrido de Atomic Code con usuario autenticado, historial persistente y runtime real; mantener Shadow Usage sin cobro.
3. Completar la revisión de aislamiento y autorización del agente, fuentes RAG y recuperación de ejecuciones.
4. Preparar aceptación de SMTP/OAuth y el subdominio admin en staging; no cambiar DNS/Nginx ni desplegar producción sin autorización específica.
5. Mantener facturación y checkout deshabilitados hasta cerrar el gate de producción y la integración QvaPay verificada.


### Readiness de IA y marca de correos — verificación adicional

La ruta `/health` ahora valida no solo que Ollama responda, sino que `/api/tags` incluya exactamente el modelo de chat configurado y el modelo de embeddings configurado (normalizando el tag implícito `:latest`). Si falta cualquiera, readiness responde HTTP 503 e identifica el componente ausente; `/health/live` continúa siendo una prueba de liveness independiente. Se añadieron pruebas para readiness correcto y para el caso de modelo de chat ausente.

Los correos de verificación y recuperación y la documentación del servicio de identidad usan ahora la identidad definitiva **AXYRON ATOMIC** en lugar de la marca heredada AXION. Se añadió una prueba de regresión de asunto y cuerpo de ambos correos.

GitHub Actions `42400165930`, commit `e3965f7944b3f330c014413e6df2d597d1249d24`, terminó en **success**: Python, Playwright, build de imagen en CI, migraciones PostgreSQL e integración Qdrant Cloud. Esta ejecución incluye la corrección HttpOnly del login, los textos de marca y la validación de modelos configurados en readiness. No hubo despliegue de VPS.


### Portal administrativo: E2E de navegador añadido

Se amplió `tests/e2e/studio-browser.mjs` para ejecutar el portal administrativo en Chromium con respuestas de API controladas: sesión válida sin rol global, disponibilidad de cierre de sesión, transición de logout a login, login que exige MFA, limpieza de la contraseña del primer factor, visualización del desafío MFA y denegación final cuando la cuenta no tiene rol administrativo. La prueba verifica que no se conceda acceso por completar MFA sin rol global.

GitHub Actions `42401029175`, commit `62c1a0321622492d01b5c02f1f5089ef501dbda0`, terminó en **success**. Los cinco trabajos pasaron: `python-tests`, `studio-browser-e2e` (incluye ahora el portal admin y MFA), `container-image-build`, `postgres-migrations` y `qdrant-cloud-integration`. El build fue de CI, no un despliegue.

### Archivos de esta mejora

- `frontend/admin.js`: separa el desafío MFA del formulario de contraseña y limpia el primer factor antes de pedir el código.
- `tests/test_frontend_studio_spa.py`: cubre el contrato de transición MFA.
- `tests/e2e/studio-browser.mjs`: prueba navegador del portal administrativo, logout, MFA y rechazo de cuentas sin rol global.


## Actualización — 7 de noviembre de 2026: ecosistema extensible de Axyron Studio

Se revisó el README principal y la implementación actual de `frontend/studio.js`. El módulo API e integraciones ya informaba de conectores pendientes, pero no explicaba de forma suficiente el alcance futuro de aplicaciones externas, plugins, skills, tools y protocolos.

Se actualizó la sección **API e integraciones** con una presentación de producto futurista:
- AXYRON CONNECT para aplicaciones y servicios externos.
- App Connectors y autorización segura.
- Plugin Hub, Skill Library y Tool Registry.
- Evaluación de MCP, APIs HTTP y webhooks.
- Control de permisos, auditoría, revocación y desconexión.
- Centro de extensiones dentro de Herramientas.

Todos estos elementos se identifican explícitamente como **Próxima actualización**. No se añadieron endpoints ficticios ni se habilitó ninguna integración que no exista en backend.

El README principal conserva su contenido anterior y ahora contiene el roadmap del ecosistema extensible, estado real, criterios mínimos de seguridad y una advertencia explícita de que el catálogo/instalador aún no está operativo.

Se añadió una prueba de contrato estático para verificar que la interfaz y README mantengan coherencia en estas promesas de roadmap.

Archivos modificados:
- `frontend/studio.js`
- `README.md`
- `tests/test_frontend_studio_spa.py`
- `docs/FRONTEND_STUDIO_STATUS.md`

La validación de CI de estos cambios queda pendiente. No se ha desplegado ni modificado el VPS.
