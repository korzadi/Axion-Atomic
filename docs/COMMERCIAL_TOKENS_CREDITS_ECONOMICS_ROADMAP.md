# AXION ATOMIC — Plan comercial, tokens, créditos y rentabilidad

**Estado:** incorporado al plan del proyecto; Fase 1 (auditoría inicial del repositorio) documentada.  
**Alcance:** planificación e integración futura en AXION ATOMIC. Este documento no habilita despliegues, cambios de infraestructura, cobros reales ni activación comercial.

## 1. Objetivo

Construir un sistema económico centralizado, auditable y extensible que mida el consumo real de inferencia por usuario, modelo y solicitud; aplique cuotas y límites desde el backend; administre créditos y suscripciones; registre costes atribuibles y fijos; y presente información diferenciada para usuarios y administradores.

La base de datos será la autoridad para saldos, reservas, límites y movimientos. El frontend nunca podrá definir ni modificar precios, cuotas, créditos o costes.

## 2. Parámetros comerciales iniciales propuestos

Estos valores son configuración inicial propuesta, no planes ya activos ni una promesa de disponibilidad. Deben residir en backend/base de datos y ser editables mediante administración autorizada.

### Cuotas de suscripción

| Plan | Tokens diarios | Tokens mensuales | Máximo de salida por solicitud |
|---|---:|---:|---:|
| FREE | 100.000 | 2.000.000 | 4.000 |
| STARTER | 500.000 | 15.000.000 | 8.000 |
| PRO | 2.000.000 | 60.000.000 | 16.000 |
| PREMIUM | 5.000.000 | 150.000.000 | 32.000 |
| ENTERPRISE | Configurable | Configurable | Configurable |

Los contadores diarios y mensuales se aplicarán simultáneamente e incluirán entrada y salida. También se configurarán RPM, concurrencia, contexto, zona horaria, duración y límites específicos del modelo. Ningún límite podrá superar la capacidad efectiva del modelo/proveedor.

### Paquetes de créditos de referencia

| Paquete | Créditos | Precio propuesto |
|---|---:|---:|
| FREE | 100.000 diarios | $0 |
| STARTER | 5.000.000 | $2.99 |
| PRO | 20.000.000 | $7.99 |
| PREMIUM | 60.000.000 | $19.99 |
| BUSINESS | 200.000.000 | $49.99 |

Los paquetes de créditos son distintos de las cuotas de suscripción. Se mantendrán libros separados para créditos gratuitos, incluidos en suscripción y comprados, con expiración, prioridad de consumo y reembolsos configurables. Conversión inicial propuesta: 1 crédito por token contabilizado. No habrá transferencias entre usuarios ni saldo negativo.

### Tarifas internas provisionales de referencia

| Categoría | Input / 1M | Output / 1M |
|---|---:|---:|
| Atomic Code 7B | $0.10 | $0.30 |
| Modelos pequeños | $0.05 | $0.15 |
| Modelos medianos | $0.20 | $0.60 |
| Modelos grandes | $0.50 | $1.50 |
| Modelos externos | Según proveedor | Según proveedor |

Son tarifas de referencia para simulación y configuración comercial, no costes medidos, precios oficiales ni afirmaciones de coste real. Cada versión de tarifa se conservará históricamente. Los costes desconocidos quedarán explícitamente como pendientes.

## 3. Auditoría inicial del repositorio (Fase 1)

### Archivos inspeccionados

- `README.md`: arquitectura, límites operativos y estado por fases.
- `api/config.py`: modelo local predeterminado, contexto, conexión DB y autenticación deshabilitada por defecto.
- `api/main.py`: composición FastAPI, rutas heredadas `/v1/*), rutas de autenticación/workspace y SPA.
- `api/workspace_routes.py`: chat, ingestión, tareas, ejecuciones y aprobaciones de proyecto.
- `api/auth_routes.py`, `api/auth.py`: usuarios, sesiones, CSRF y roles de membresía de proyecto.
- `api/schemas.py`: contrato de ChatRequest y límites de payload.
- `api/ollama.py`: llamada no streaming a Ollama y extracción actual solo del texto.
- `api/database.py`, `rag/meta.py`: SQLAlchemy para PostgreSQL y MetaStore auxiliar.
- `migrations/001_initial.sql`: esquema inicial existente.
- `agent/run_store.py`, `agent/approval_store.py`: persistencia/idempotencia de ejecuciones y aprobación, no billetera comercial.
- `frontend/index.html`: SPA y vistas de usuario; navegación de administración aún no constituye un backend administrativo.

### Hallazgos verificables

1. **Inferencia actual:** `api/ollama.py` llama a `/api/chat` con `stream=false`, recibe el JSON del motor y devuelve únicamente `message.content`. No expone ni persiste `prompt_eval_count`, `eval_count`, duración ni otros contadores de la respuesta. Existe un punto de integración para medición real, pero aún no hay contabilización por usuario/solicitud.
2. **Modelo y contexto:** `api/config.py` fija `chat_model=atomic-code:16k-8k` y `num_ctx=16384`. `ChatRequest` acepta `max_tokens` hasta 8192 y el modelo del cliente no gobierna la selección real. La respuesta informa `settings.chat_model`. Esto no reemplaza un Model Router ni una verificación de capacidad por modelo.
3. **Autenticación:** hay usuarios, sesiones, Argon2, CSRF y membresías por proyecto. Sin embargo, `auth_enabled` está deshabilitado por defecto; el registro deja la cuenta en `pending_verification` y no se verificó flujo de correo. No debe activarse como parte de esta auditoría.
4. **Identidad de API:** `/workspace/chat/completions` usa sesión/CSRF y autorización de proyecto. La API heredada `/v1/*` usa una clave global de servicio sin identidad individual; `legacy_api_enabled` permanece cerrado por defecto. No es suficiente para facturar usuarios individualmente.
5. **Base de datos:** existe PostgreSQL como backend configurado y una migración inicial para aprobaciones, proyectos, tareas y versiones de modelos. En los archivos inspeccionados no aparecen tablas de planes, suscripciones, uso de tokens, costes, créditos, libro contable, reservas ni auditoría económica.
6. **Administración:** no se encontró una API administrativa económica integrada. La navegación administrativa del frontend no acredita RBAC global ni capacidad de modificar planes, costes o cuentas.
7. **Facturación:** README contempla un Payment Manager intercambiable con QvaPay. Esta auditoría no encontró un flujo técnico de suscripciones, checkout, webhooks, conciliación o reembolsos implementado. El estado comercial aprobado de QvaPay comunicado por el propietario no significa integración técnica completada.
8. **Costes:** no se identificó telemetría de CPU/RAM/GPU/almacenamiento facturada por usuario ni un inventario verificable de tarifas de proveedores. No se asignan valores inventados.
9. **Redis:** su uso para coordinación o contadores no fue demostrado por los archivos revisados. PostgreSQL debe conservar autoridad transaccional sobre los saldos y movimientos.
10. **Seguridad económica:** aún no existen reservas de cuota/crédito ni reconciliación idempotente de inferencia. No se deben vender créditos ni habilitar cobros hasta implementar y probar estas garantías.

### Estado de Fase 1

**Auditoría inicial de repositorio: completada para los componentes enumerados; auditoría integral: pendiente.** No se inspeccionó ni modificó el VPS, no se verificaron facturas reales, no se ejecutaron pruebas ni migraciones, y no se validaron proveedores externos. Los hallazgos describen el código fuente revisado, no el estado operativo de infraestructura.

## 4. Diseño técnico objetivo

### Medición y registro de inferencia

Cada petición deberá tener un identificador idempotente generado/validado por backend y registrar como mínimo: usuario, organización/workspace cuando aplique, modelo y versión, plan efectivo, tokens de entrada/salida/total, timestamps, duración, estado, proveedor, tarifa versionada, coste estimado, coste real y metadatos de reconciliación.

- Preferir contadores reales del motor/proveedor (en Ollama, campos de evaluación de la respuesta no streaming); no confiar en tokens declarados por el cliente.
- Si un motor no proporciona conteo exacto, usar tokenizer identificado/versionado como estimación explícita; no etiquetarlo como medición real.
- Mantener separados coste interno estimado, coste facturado por proveedor, precio comercial y coste de infraestructura atribuible.
- Guardar una instantánea de la tarifa aplicada para que cambios posteriores no reescriban operaciones históricas.
- Resolver fallos, cancelaciones, timeouts y respuestas parciales con estados de reconciliación; no cobrar tokens no producidos ni duplicar un evento.

### Cuotas, reservas y concurrencia

Flujo obligatorio: autenticación e identidad → plan y excepciones backend → cuota diaria/mensual → saldo y prioridad de créditos → máximo de salida/contexto/modelo → RPM/concurrencia → reserva atómica → inferencia → reconciliación de consumo real → liberación de reserva no utilizada.

La reserva debe ser atómica en PostgreSQL, con bloqueo/actualización condicional o mecanismo equivalente, clave idempotente y vencimiento/reconciliación de reservas huérfanas. Redis, si se incorpora, será auxiliar para coordinación y nunca autoridad final del saldo. Zona horaria y ventanas de renovación deben estar configuradas explícitamente.

### Libros de créditos y suscripciones

Usar libro inmutable de movimientos (otorgamiento, reserva, consumo, liberación, vencimiento, compra y reembolso), con categorías separadas, lotes/expiración y saldo derivado o protegido por transacción. No permitir edición directa de movimientos ni saldos negativos. La prioridad de consumo será configuración versionada.

Los planes, precios, paquetes, excepciones individuales y promociones tendrán historial de cambios con actor, timestamp, valor anterior/nuevo y motivo. La autorización administrativa será independiente de la membresía de proyecto.

### Economía e infraestructura

Cálculos:
- coste de input = input_tokens / 1.000.000 × tarifa_input;
- coste de output = output_tokens / 1.000.000 × tarifa_output;
- coste atribuible = input + output + extras medidos atribuibles;
- margen bruto = (ingresos − costes directos) / ingresos × 100, solo si ingresos > 0.

Separar margen bruto de beneficio neto. Costes fijos mensuales (servidor, almacenamiento base, mantenimiento, etc.) se reportan una sola vez en el periodo; no se duplican al sumarlos por usuario. El coste por usuario puede mostrar coste variable atribuible y una asignación fija explícita, con método documentado. El punto de equilibrio debe indicar supuestos y periodo.

## 5. Fases de implementación

| Fase | Alcance | Criterio de salida |
|---|---|---|
| 1. Auditoría | Inventario de API, auth, DB, inferencia, planes/pagos, admin, infraestructura y pruebas | Hallazgos, brechas, riesgos y dependencias documentados |
| 2. Diseño | Modelo de datos, estados, transacciones, tarifas, reglas de crédito y amenazas | Diseño revisado antes de migrar |
| 3. Medición | Captura de tokens reales/estimados, duración y estados de solicitud | Pruebas con respuestas de motor y errores |
| 4. Costes de modelos | Tarifas versionadas, coste estimado/real y proveedores | Cálculos exactos y tarifas históricas |
| 5. Créditos | Libro, lotes, expiración, reservas, reembolsos | Atomicidad, idempotencia y no saldo negativo |
| 6. Planes/cuotas | Planes, ciclos, excepciones, límites diario/mensual | Cuotas concurrentes no superables |
| 7. Concurrencia | RPM, slots, reservas, expiración y reconciliación | Carrera, caída y retry cubiertos |
| 8. Administración | RBAC global, planes, tarifas, costes, suspensiones y auditoría | Solo roles autorizados; cambios auditados |
| 9. Panel de usuario | Plan, créditos, consumo, cuotas, historial y avisos 70/90/100% | Datos derivados del backend, aislados por usuario |
| 10. Rentabilidad | Ingresos, costes, margen, coste por modelo/usuario y break-even | Sin costes ni métricas inventados |
| 11. Seguridad y pruebas | 15 escenarios obligatorios, abuso, aislamiento, migraciones y concurrencia | Suite ejecutada con resultados registrados |
| 12. Documentación | Operación, tarifas, reconciliación, administración y reporte | Documentación consistente con lo desplegado |

Cada fase se cerrará con: estado, archivos, cambios, funciones, pruebas realmente ejecutadas, resultados, problemas, riesgos, costes reales identificados, costes pendientes y siguiente fase. No pasar de diseño a implementación sin registrar los criterios de aceptación.

## 6. Pruebas obligatorias

La suite debe verificar los 15 escenarios definidos por el propietario: cuotas diaria/mensual; planes de pago; concurrencia y saldo; fallo sin cobro indebido; tokens input/output; tarifas por modelo e histórico; manipulación de créditos; cambios administrativos; separación de categorías; renovación por zona horaria; funcionamiento CPU-only; tarifas de proveedores externos; y ausencia de saldos negativos.

Añadir pruebas de doble webhook, repetición de petición, timeout tras inferencia, proceso muerto entre reserva y reconciliación, reserva expirada, modificación concurrente de plan, cambio de tarifa durante petición y autorización de administrador.

## 7. Riesgos y decisiones pendientes

- Confirmar zona horaria comercial y calendario de renovación.
- Definir si la cuota de suscripción y los créditos comprados se consumen ambos o si una modalidad sustituye a la otra en casos concretos.
- Definir tratamiento de tokens de prompt de sistema, historial y RAG.
- Determinar tokenizer y precisión de conteo para cada modelo/proveedor.
- Definir política de streaming antes de habilitarlo; actualmente no está implementado.
- Definir quién puede ejercer rol de administrador global y el proceso de recuperación.
- Obtener facturas y precios reales de VPS, almacenamiento, dominios, APIs y otros proveedores.
- Definir impuestos, moneda, devoluciones, disputas y obligaciones comerciales con asesoría adecuada.
- Definir si las tarifas propuestas de créditos y planes son solo referencias o serán aprobadas comercialmente en una etapa posterior.

## 8. Límites de protección

- No activar auth, pagos, ventas ni cobros reales por esta documentación.
- No desplegar, reconstruir/reiniciar Docker ni operar servicios/VPS sin autorización expresa.
- No modificar Ollama, modelos, servicios ajenos ni secretos.
- No inventar facturas, coste de GPU, electricidad, precios de proveedor o métricas.
- No borrar ni sustituir funciones existentes.
- No añadir Open WebUI.
- No publicar credenciales ni datos privados.
- Toda migración será aditiva, revisada y reversible cuando sea técnicamente posible; no ejecutar migraciones sin autorización expresa.

## 9. Próxima acción

Continuar completando la auditoría estática de todos los módulos de API, composición de dependencias, pruebas y migraciones; después presentar el diseño de datos y el flujo transaccional de reservas/créditos para revisión antes de escribir código económico.


## 10. Auditoría ampliada de API, identidad e interfaz (6 de noviembre de 2026)

Esta ampliación se basa en lectura estática de los archivos indicados en GitHub. No se ejecutó el backend, no se conectó a PostgreSQL/Ollama, no se ejecutaron pruebas y no se inspeccionó el VPS.

### Composición HTTP y rutas

- `api/main.py` registra `auth_router` y `workspace_router`; el frontend estático se monta al final. No se observó un router de administración económica ni de billing en esta composición.
- `POST /workspace/chat/completions` autentica sesión, valida CSRF y comprueba membresía de proyecto. Después llama a la inferencia sin registrar uso económico ni reservar cuota/créditos.
- `POST /v1/chat/completions` y las rutas heredadas `/v1/knowledge/*` y `/v1/agent/*` dependen de `require_api_key`. `api/security.py` rechaza la API heredada cuando `legacy_api_enabled=false`; si se habilitara, la clave compartida seguiría sin identificar a un usuario ni delimitar por sí sola el proyecto.
- Las rutas de workspace implementan autorización de membresía por proyecto. Los roles `owner/admin/editor/viewer` son roles de proyecto; no son un rol administrativo global para gestionar tarifas, planes, saldos o usuarios.
- Las rutas de aprobaciones de proyecto devuelven explícitamente `execution: not_executed` al registrar decisiones. No constituyen un mecanismo de facturación ni de ejecución automática.

### Identidad, registro y sesiones

- `api/auth.py` implementa hash de contraseña Argon2, sesiones opacas almacenadas como digest SHA-256, expiración de 12 horas, revocación y validación CSRF.
- El registro inserta usuarios con estado `pending_verification`. En los archivos de rutas inspeccionados no aparece un endpoint de verificación de correo ni un flujo de emisión/consumo de tokens de verificación. La autenticación solo acepta usuarios `active`.
- `auth_enabled` está deshabilitado por defecto en `api/config.py`; las rutas web fallan de forma cerrada mientras siga desactivado.
- No se observó limitación de intentos de login ni rate limiting en los módulos de autenticación inspeccionados. Antes de habilitar registro/login se debe auditar e implementar protección antiabuso distribuida y controles de recuperación/verificación.
- La cookie de sesión es HttpOnly; la cookie CSRF se expone al frontend para enviarla como header. La cookie segura depende de `auth_cookie_secure`, configurada a true por defecto.

### Contrato de chat y medición

- `api/schemas.py` permite roles `user/assistant`, mensajes de 1 a 20.000 caracteres, hasta 100 mensajes, `max_tokens` de 1 a 8.192 y `stream=false` por defecto. El campo `model` tiene un valor por defecto, pero no se usa para seleccionar el modelo en las rutas revisadas.
- `api/ollama.py` solicita el modelo fijado en configuración, contexto `num_ctx`, `num_predict` y respuesta no streaming. La función descarta el resto del JSON y retorna solo `message.content`; debe evolucionar a un resultado tipado que conserve modelo devuelto, contadores, duración, estado y metadatos disponibles.
- La ruta de chat informa `settings.chat_model` como modelo de respuesta. Ese dato es el modelo configurado solicitado, no una prueba independiente del modelo realmente servido por el motor.
- El límite de salida del esquema no sustituye las cuotas económicas: actualmente no existe reserva previa, contador por usuario, ni reconciliación de consumo real.

### Persistencia, migraciones y administración

- `api/database.py` crea un engine SQLAlchemy compartido desde `database_url`; el archivo inspeccionado no contiene un gestor de migraciones.
- La migración `migrations/001_initial.sql` inspeccionada contiene tablas de proyectos, aprobaciones, tareas, acciones, fuentes de conocimiento y versiones de modelos. No contiene tablas económicas.
- `api/projects.py` y `api/project_creation.py` operan proyectos/membresías y workspace; no son servicios de suscripción ni de saldo.
- No se encontró una ruta de administración global en `api/main.py` ni en los routers inspeccionados. La vista Admin de `frontend/index.html` indica que necesita endpoints administrativos y RBAC verificado; la interfaz no otorga privilegios.
- El frontend es una SPA estática en `frontend/index.html`. La vista de chat llama a la ruta real de workspace; las vistas de modelos, agentes, vídeo y administración se presentan como módulos pendientes de integración, no como paneles económicos ya funcionales.
- Se verificó el archivo `tests/test_auth_routes.py`, que contiene pruebas unitarias de la puerta de autenticación y validación básica de esquemas. No se verificó en esta lectura una suite completa de billing, medición, cuotas, créditos, pagos o concurrencia. La existencia de otros tests no se infiere a partir de los archivos consultados.

### Impacto en el plan económico

1. La medición y el cobro deben integrarse en el límite común de inferencia utilizado por las rutas web y cualquier API futura con identidad individual; no deben duplicarse reglas de negocio dentro de cada endpoint.
2. Antes de crear reservas económicas, hay que definir identidad canónica (usuario, organización/workspace y proyecto), idempotency key, ciclo de vida de la petición y cómo se vinculan una reserva y su reconciliación.
3. El futuro RBAC administrativo debe ser global y separado de los roles de proyecto. Nunca se debe inferir que un `owner` de proyecto puede editar precios o saldos.
4. El flujo de verificación de correo, recuperación de cuenta y rate limiting debe resolverse antes de habilitar el registro público o comercial.
5. Las tablas de uso, tarifas, reservas, créditos y auditoría deben añadirse mediante migraciones nuevas, aditivas y revisables; no alterar la migración inicial ni ejecutar migraciones como parte de esta fase.

### Estado actualizado de Fase 1

**Auditoría estática ampliada de la ruta principal de chat, autenticación, seguridad de API, persistencia, composición HTTP y SPA: completada para los archivos enumerados.** La auditoría integral del repositorio sigue pendiente de inventario exhaustivo de módulos, migraciones, pruebas, proveedores de pago y costes operativos. No se ejecutaron pruebas, migraciones ni inferencias.


## 11. Inventario ampliado del repositorio y precisión de migraciones (6 de noviembre de 2026)

Se enumeraron los contenidos de `api/`, `agent/`, `rag/`, `migrations/`, `tests/`, `frontend/`, `docs/` y `.github/workflows/` en la rama `main`. La enumeración no equivale a una auditoría línea por línea de cada módulo.

### Migraciones y motor de migración: corrección importante

La inspección ampliada confirma que el repositorio sí dispone de un migrador versionado: `api/migrate.py`. La frase anterior que decía que `api/database.py` no contenía un gestor de migraciones se refería solo a ese archivo, no al repositorio completo. El migrador:
- descubre archivos `NNN_nombre.sql` en `migrations/`;
- registra versión, nombre, checksum y fecha en `schema_migrations`;
- utiliza advisory lock PostgreSQL;
- ejecuta cada migración en una transacción;
- aborta si cambia el checksum de una migración ya aplicada.

Migraciones existentes identificadas:
- `001_initial.sql`: proyectos, aprobaciones, tareas, acciones y versiones de modelos.
- `002_rag_memory.sql`: índice RAG y memorias por proyecto.
- `003_approvals_audit.sql`: aprobaciones de acciones y auditoría encadenada del runtime.
- `004_agent_run_persistence.sql`: ejecuciones y acciones persistentes del agente.
- `005_identity_sessions_memberships.sql`: usuarios, sesiones y membresías de proyecto.

Las cinco migraciones revisadas no contienen el sistema comercial propuesto. Hay una carpeta `migrations/rollback/`; sus archivos deben auditarse antes de definir cualquier procedimiento de reversión. No se ejecutó el migrador.

### Suite y CI

Se identificaron más de cuarenta módulos de prueba en `tests/`, que cubren API, seguridad, autenticación, modelos, Ollama, RAG, proyectos, workspace, runtime, aprobaciones, sandbox y persistencia. No se encontró suite comercial de cuotas, créditos, facturación, pagos o concurrencia económica en el inventario. Esto describe nombres/alcance aparente; no certifica que todas las pruebas pasen.

`.github/workflows/ci.yml` configura Python 3.12, instalación desde `requirements.txt`, `compileall` y `pytest -q` usando SQLite para CI. Por tanto, el CI actual no valida por sí solo semántica específica de PostgreSQL como `FOR UPDATE`, advisory locks, constraints transaccionales ni concurrencia real. Fase de billing deberá añadir pruebas PostgreSQL compatibles antes de aceptar las garantías económicas.

### QvaPay

`docs/QVAPAY_INTEGRATION_STATUS.md` declara aprobación comercial comunicada por el propietario como `APPROVED`, integración técnica en desarrollo y ausencia de cobros reales. Documenta contrato de factura, verificación servidor, firma HMAC del webhook, timestamp, conciliación y clave idempotente `transaction_uuid`. Esta especificación sirve de base, pero la implementación debe verificarse con el simulador oficial y sin secretos en el repositorio.

### Costes reales y telemetría

La lectura de archivos del repositorio no proporciona facturas ni mediciones atribuibles de VPS, CPU, RAM, almacenamiento, GPU externa, electricidad o servicios auxiliares. Los costes de infraestructura permanecen desconocidos/no verificados. Las tarifas por millón y precios de planes/paquetes en este roadmap siguen siendo valores de referencia, no precios activos ni costes reales.

### Estado de Fase 1 tras inventario

**Inventario estructural de las carpetas principales y lectura de migraciones, CI y estado QvaPay: completados.** La auditoría de cada módulo no es exhaustiva y la auditoría de costes reales requiere documentación/facturas que no se encuentran en el repositorio. No se ejecutaron tests, CI, migraciones, inferencias ni llamadas de pago.

## 12. Diseño técnico de Fase 2

Se ha añadido el documento [COMMERCIAL_BILLING_TECHNICAL_DESIGN.md](COMMERCIAL_BILLING_TECHNICAL_DESIGN.md), con el modelo relacional propuesto, límites de identidad, medición, tarifas versionadas, reservas, cuotas, créditos, pagos QvaPay, costes de infraestructura, idempotencia, concurrencia, errores, seguridad, migraciones y criterios de aceptación.

El diseño recomienda comenzar con facturación individual por `user_id`, mantener `project_id` como dimensión de atribución y dejar organizaciones para una decisión explícita; usar PostgreSQL como autoridad; separar el ledger inmutable de créditos del contador de cuota; y no mantener transacciones/locks DB durante inferencias.

**Fase 2: diseño técnico actualizado con decisiones de política autorizadas por el propietario; no implementado.** Las reglas iniciales quedan registradas en `COMMERCIAL_BILLING_TECHNICAL_DESIGN.md`: cuota FREE → cuota de suscripción → créditos comprados; expiración por tipo; UTC predeterminado; fallback a créditos comprados solo si el plan lo permite; ponderadores de crédito por modelo/tipo de token; titularidad individual inicial. Los planes, precios y tarifas de referencia no están publicados ni activos. No se ha creado código económico ni se han activado cobros.


## 13. Decisiones de política aprobadas y siguiente ejecución (6 de noviembre de 2026)

El propietario autorizó expresamente al equipo a resolver las seis decisiones de política que estaban pendientes. Se registraron como reglas iniciales versionadas en el diseño técnico:

1. Prioridad: cuota gratuita diaria → cuota incluida de suscripción → créditos comprados FEFO.
2. Expiración: cuota diaria al cierre del día; cuota incluida al final del ciclo, sin rollover inicial; créditos comprados con ventana inicial de 12 meses, pendiente de validación legal/comercial antes de vender.
3. Zona horaria: UTC predeterminado; persistir zona IANA y límites UTC exactos.
4. Sobreconsumo: permitir créditos comprados únicamente cuando el plan habilite ese fallback; nunca saldo negativo.
5. Conversión: unidad base 1 crédito/token, con ponderadores versionados por modelo y separado input/output. Atomic Code inicia en 1/1 para simulación; no se activa facturación.
6. Titularidad: cuenta individual por usuario; proyecto solo como atribución; organizaciones después.

### Próximas tareas técnicas

- Completar revisión de los scripts de rollback y de los módulos de autenticación/administración antes de diseñar las migraciones definitivas.
- Revisar y cerrar las pruebas de contrato/CI del adaptador tipado y Shadow Mode.
- Diseñar persistencia append-only en PostgreSQL para observaciones, con idempotencia, permisos y privacidad, sin introducir cobro.
- Incorporar pruebas de contrato y PostgreSQL para medición, idempotencia, transacciones y concurrencia antes de activar reservas.
- No publicar planes/precios como activos, no habilitar pagos ni ejecutar migraciones de producción hasta superar las pruebas y la revisión comercial/legal.

**Autorización recibida:** cubre elegir y documentar las políticas de diseño. No constituye autorización para cobros reales, compras, cambios de infraestructura, despliegues o migraciones en VPS.


## 14. Auditoría de scripts de reversión (6 de noviembre de 2026)

Se inspeccionaron los dos archivos existentes en `migrations/rollback/`:

- `002_down.sql` elimina las tablas RAG y memoria de proyecto y borra su marca de migración.
- `003_down.sql` elimina aprobaciones de acciones y auditoría encadenada y borra su marca de migración.
- No hay scripts down identificados para 001, 004 y 005.

Ambos scripts existentes son destructivos por diseño y no representan una reversión segura para producción. En particular, podrían borrar datos de proyecto, memoria, aprobaciones o auditoría. **No se ejecutaron.** Las futuras migraciones comerciales serán forward-only por defecto; si se necesita corregir esquema, se añadirá una migración compensatoria que preserve datos. El ledger económico jamás se revertirá borrando movimientos: se utilizarán asientos compensatorios.

El migrador actual verifica checksum, usa advisory lock PostgreSQL y ejecuta cada migración en transacción. No se ejecutó ninguna migración.


## 15. Contrato de inferencia y alcance de medición (6 de noviembre de 2026)

La inspección directa de las rutas y del adaptador de Ollama confirmó que la implementación anterior devolvía solo texto y descartaba los contadores. Esa brecha ya se corrigió en Shadow Mode: el adaptador conserva prompt_eval_count y eval_count reportados por Ollama. La ruta autenticada `/workspace/chat/completions` compone system prompt y contexto RAG del lado servidor antes de inferir. Por ello, el input real se mide desde prompt_eval_count y no se estima sumando textos en la API. Los campos ausentes quedan NULL, nunca cero.

La API heredada `/v1` utiliza una clave compartida y no puede atribuir consumo a una persona; permanece fuera de billing individual. Streaming sigue deshabilitado.

El contrato `InferenceResult` y la primera fase de código en modo **shadow** están publicados: capturan identidad, proyecto, modelo, contadores y duración sin bloquear solicitudes, sin descontar créditos, sin crear saldo y sin cobrar. El fallo de telemetría no debe hacer fallar una inferencia que ya fue exitosa.

***Estado actualizado:** el contrato tipado y la medición inicial en Shadow Mode ya están publicados en `api/ollama.py` y `api/workspace_routes.py`; las pruebas focalizadas están añadidas en `tests/test_ollama_usage.py` y `tests/test_workspace_role_matrix_http.py`, pero su ejecución y el CI siguen pendientes de verificación. No existe todavía persistencia PostgreSQL, facturación, ledger, reservas, cuotas activas ni cobros.

## 16. Actualización de Shadow Mode y pruebas pendientes (6 de noviembre de 2026)

La implementación inicial de Shadow Mode se publicó en `main`:
- `api/ollama.py`: `InferenceResult`, validación de contadores y `chat_with_usage()`; `chat()` conserva compatibilidad devolviendo texto.
- `api/workspace_routes.py`: la ruta autenticada usa el resultado tipado y emite un evento JSON de observación sin incluir prompts ni respuestas.
- `tests/test_ollama_usage.py`: pruebas de parsing, petición HTTP no streaming, propagación de timeout y compatibilidad del wrapper.
- `tests/test_workspace_role_matrix_http.py`: pruebas HTTP actualizadas para el nuevo adaptador, comprobación de respuesta, ausencia del texto del usuario en el evento de log y aislamiento ante fallo del logger.
- `tests/test_model_identity.py` y `tests/test_workspace_authorization_boundaries.py`: mocks actualizados al adaptador tipado para retirar referencias obsoletas a `workspace_routes.chat`.

**Verificación:** los archivos de prueba están publicados, pero no se ha confirmado todavía una ejecución satisfactoria de pytest ni de GitHub Actions. La actualización de pruebas evita depender de `pytest-asyncio`, que no figura entre las dependencias fijadas del proyecto.

**Siguiente paso:** confirmar CI; después añadir pruebas de fallo de telemetría y persistencia append-only en PostgreSQL de prueba. No activar reservas, cuotas ni cobros.

## 17. Diseño de persistencia Shadow Mode (6 de noviembre de 2026)

Se publicó `docs/SHADOW_USAGE_POSTGRESQL_DESIGN.md` como propuesta técnica para almacenar observaciones de inferencia en PostgreSQL. Define una tabla append-only con identidad individual, atribución opcional al proyecto, request_id idempotente, contadores y duraciones de Ollama, permisos de solo inserción/lectura y pruebas PostgreSQL requeridas. No crea migraciones ni tablas y no activa facturación. El siguiente paso es cerrar CI y validar el contrato en PostgreSQL efímero de CI antes de crear la migración 006.


## 18. CI con PostgreSQL efímero

Se añadió un job independiente `postgres-migrations` a `.github/workflows/ci.yml`. Usa PostgreSQL 16 efímero, aplica las cinco migraciones versionadas dos veces para verificar idempotencia y ejecuta `tests/test_postgres_migrations.py` para comprobar tablas, relaciones, restricciones e índices del esquema actual. El job todavía debe completar satisfactoriamente en GitHub Actions. Esta verificación no crea ni prueba aún la tabla de telemetría `inference_usage_events` y no implica cambios en bases de datos reales.


## 18. Estado real de medición Shadow Mode y correcciones de validación (7 de noviembre de 2026)

Esta sección **sustituye las afirmaciones anteriores de las secciones 15–17 que quedaron desactualizadas**.

### Implementado en main

- `api/ollama.py` conserva `InferenceResult`, contadores reales de Ollama y duraciones; los valores inválidos/ausentes permanecen `NULL`/`None`.
- `migrations/006_inference_usage_events.sql` crea `inference_usage_events` con identidad, proyecto, modelo, contadores, duraciones, timestamp e índices.
- `api/usage_events.py` persiste observaciones en PostgreSQL mediante transacción breve y `ON CONFLICT (request_id) DO NOTHING`.
- `/workspace/chat/completions` genera un UUID y persiste la observación sin prompts, respuestas ni secretos. La escritura es best-effort: un fallo de PostgreSQL no interrumpe una inferencia ya aceptada y puede perderse el evento.
- La ruta heredada `/v1` continúa fuera de medición individual. Shadow Mode no crea saldos, créditos, reservas, cuotas ni cobros.

### Endurecimiento añadido el 7 de noviembre

La revisión encontró que la ruta intentaba guardar contadores antes de validar que el modelo devuelto coincidiera con el modelo autorizado y que la inferencia hubiera terminado. Se corrigió el orden: ahora solo se persiste uso después de superar ambas validaciones. Se añadieron pruebas HTTP para comprobar que un modelo inesperado o una inferencia incompleta no generan eventos de uso ni historial de chat.

### Estado de validación

- La persistencia PostgreSQL best-effort está implementada; no debe marcarse como pendiente de implementación.
- La prueba unitaria de mapeo y la prueba de esquema PostgreSQL existen.
- El CI completo anterior confirmó migraciones y pruebas de PostgreSQL; la ejecución específica del endurecimiento del 7 de noviembre está pendiente de resultado.
- No existe todavía outbox/reintento durable, consultas de consumo para usuarios, medición completa de concurrencia ni conciliación económica.
- No se permite usar estos eventos como libro contable ni habilitar cobros.

### Desglose actualizado de Fase comercial 3 — Medición

| Submódulo | Avance |
|---|---:|
| Contrato InferenceResult y contadores Ollama | 100% |
| Integración con chat autenticado | 100% |
| Persistencia PostgreSQL best-effort e idempotencia por request_id | 100% código |
| Validación de modelo y finalización antes de persistir | 100% código; CI pendiente |
| Pruebas de parsing y persistencia | 100% código; ejecución específica pendiente |
| Outbox y reintentos durables | 0% |
| Consultas de consumo autenticadas | 0% |
| Pruebas de concurrencia y recuperación | 0% |
| Conciliación de medición | 0% |

**No se activan reservas, cuotas, ledger, pagos ni cobros.** La Fase comercial 3 no se considera cerrada hasta aprobar CI, definir garantía de entrega y completar los criterios de aceptación de esta fase.
