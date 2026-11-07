# Estado de AXION STUDIO — frontend web

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
- Agente ejecutor: faltan inicio/reanudación persistente, recuperación de tareas interrumpidas, eventos y aprobación ligada al hash de la acción.

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

- Navegación integrada: Resumen, Proyectos, Atomic Code, Conocimiento, Agente Axyron, Modelos Atomic, Consumo, Facturación, Cuenta y seguridad y Administración.
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
