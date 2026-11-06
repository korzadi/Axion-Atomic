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
- Conocimiento: interfaz conectada para indexar texto y cargar PDF/DOCX/TXT/Markdown (máximo 5 MB y 100000 caracteres extraídos), listar fuentes por proyecto, reindexar fuentes administrables y eliminarlas. La carga usa CSRF, valida rol y limita solicitudes; la recuperación RAG del chat queda filtrada por proyecto. No hay OCR: los PDF escaneados sin texto extraíble se rechazan. Las pruebas de contrato y rutas cubren buena parte del flujo, pero falta una prueba de navegador y una validación end-to-end contra servicios de prueba reales.
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

1. Completar CI y pruebas de integración del ciclo de fuentes (carga, indexación, listado, reindexación, recuperación y eliminación); validar en navegador y con servicios de prueba. OCR de PDF escaneados queda como mejora posterior al MVP.
2. Completar el runtime persistente del agente y su ciclo de aprobación/reanudación.
3. Completar la experiencia de Atomic Code y el módulo de conocimiento usando únicamente endpoints reales.
4. Validar OAuth, correo y configuración de autenticación en un entorno de pruebas.
5. Completar los gates de facturación y pagos sin habilitar cobros prematuramente.
6. Validar build e instalación en un entorno autorizado antes de cualquier despliegue.

## Estado operativo

Los cambios de código se guardan en el repositorio. No se ha accedido al VPS, construido o reiniciado Docker, aplicado migraciones, cambiado variables de entorno, alterado servicios ni modificado datos.
