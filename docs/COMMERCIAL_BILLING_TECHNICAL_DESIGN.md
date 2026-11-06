# Diseño técnico — economía, medición, cuotas y créditos de AXION ATOMIC

**Estado:** diseño parcialmente implementado; la base de reservas/ledger está en el repositorio, pero no está conectada a inferencia ni habilita cobros  
**Fecha:** 6 de noviembre de 2026  
**Alcance:** Fase 2 del roadmap comercial. Este documento no activa pagos, créditos, límites ni migraciones.

## 1. Objetivos y límites

Diseñar un sistema transaccional que registre el uso real de modelos, aplique cuotas y créditos sin saldo negativo, mida costes con tarifas versionadas y permita conciliar pagos. PostgreSQL será la autoridad. Redis podrá acelerar límites temporales, pero nunca decidirá el saldo ni la elegibilidad económica definitiva.

Se conserva la arquitectura actual: FastAPI, SQLAlchemy, PostgreSQL y adaptadores de inferencia. No se modifica Ollama ni se asume que existan proveedores externos activos. Los IDs de usuario actuales son TEXT y los proyectos existentes usan IDs TEXT; las nuevas relaciones deben respetar esos tipos y sus claves foráneas.

## 2. Identidad y ámbito de facturación

### Estado actual

- Hay usuarios y membresías de proyecto.
- No se encontró entidad Organization/Workspace comercial en las migraciones actuales.
- Un rol owner/admin/editor/viewer es exclusivamente de proyecto; no concede administración económica global.
- La API heredada usa una clave compartida y no puede recibir crédito individual con seguridad.

### Decisión propuesta

Primera entrega: facturación individual por `user_id`, con `project_id` opcional como dimensión de atribución, nunca como titular del saldo. Mantener preparada una columna `billing_subject_type/id` para evolución a organizaciones, pero no introducir organizaciones ficticias ni migrar usuarios a ellas en esta fase.

Toda inferencia facturable debe provenir de una identidad autenticada. Las rutas de API compartida heredadas no participan en billing hasta que tengan credenciales individuales con alcance y propietario verificable.

## 3. Modelo relacional propuesto

Las tablas de cuotas, lotes, reservas, asignaciones y ledger están creadas por las migraciones 007/008. El servicio inicial está en `api/billing_reservations.py`; el resto de las entidades descritas en esta sección continúa siendo diseño pendiente. Los nombres y tipos finales del resto se ajustarán a las convenciones del repositorio.

### 3.1 Catálogo comercial

| Tabla | Responsabilidad | Campos/constraints esenciales |
|---|---|---|
| `billing_plans` | Identidad estable del plan | `id`, `code UNIQUE`, `active`, timestamps |
| `billing_plan_versions` | Versiones inmutables de reglas | `plan_id`, `version`, `limits_json`, `credit_policy`, `effective_from/to`, UNIQUE(plan,version) |
| `billing_subscriptions` | Suscripción vigente/histórica | `user_id`, `plan_version_id`, estado, periodo, zona horaria, proveedor |
| `billing_entitlements` | Excepciones o promociones | titular, tipo, valor, vigencia, motivo, actor, estado |

Las versiones publicadas no se editan en sitio. Un cambio crea una nueva versión efectiva en una fecha explícita. Una petición guarda la versión aplicada para que una actualización posterior no altere el pasado.

### 3.2 Modelos y tarifas

| Tabla | Responsabilidad |
|---|---|
| `billing_models` | Identidad de modelo/proveedor, capacidades y tokenizer identificados |
| `billing_rate_versions` | Tarifas input/output por modelo, moneda, unidad, vigencia, fuente y estado de verificación |

La tarifa tendrá precisión decimal suficiente (por ejemplo NUMERIC, nunca FLOAT). Se distinguen tarifa comercial al usuario y coste directo del proveedor. La tarifa interna provisional de Atomic Code ($0.10/$0.30 por millón) es solo simulación y no se registra como coste real ni se activa por defecto.

### 3.3 Peticiones y uso

| Tabla | Responsabilidad | Reglas |
|---|---|---|
| `billing_usage_requests` | Una petición lógica de inferencia | UUID, user, project opcional, provider/model, plan/rate version, idempotency key, estado, timestamps, duración |
| `billing_usage_measurements` | Resultado de medición | input/output/total tokens, fuente del contador, precisión real/estimada, metadatos permitidos |
| `billing_usage_costs` | Desglose económico | coste input/output/proveedor/infra atribuible, moneda, tarifa snapshot, estado estimado/conciliado |

Constraints:
- UNIQUE(user_id, idempotency_key) para petición lógica.
- La misma clave con payload hash distinto devuelve conflicto; nunca reutiliza una reserva para otro prompt.
- Contadores no negativos; total se calcula/valida contra input + output según política documentada.
- Los tokens no disponibles quedan NULL con motivo; no se convierten silenciosamente en cero.
- Los datos del cliente nunca son autoridad para tokens ni costes.

La medición de Ollama debe capturar, cuando existan, `prompt_eval_count`, `eval_count`, `total_duration`, `load_duration`, `prompt_eval_duration` y `eval_duration`. Guardar fuente, unidad y versión del motor. Un tokenizer fallback se etiqueta `estimated` y su versión queda registrada.

### 3.4 Cuotas y reservas

| Tabla | Responsabilidad |
|---|---|
| `billing_quota_periods` | Contador por titular, tipo de ventana y periodo |
| `billing_reservations` | Reserva previa de cuota/créditos para una petición |
| `billing_reservation_allocations` | Desglose de qué cuota/lote de crédito se reservó |

Estados de petición: `created → reserved → running → succeeded/failed/partial/unknown → reconciled`. Una petición que pierde conexión con el motor puede quedar `unknown`; no debe liberarse ni cobrarse a ciegas. Un reconciliador debe recuperar el resultado si el motor lo permite o marcar la incidencia para tratamiento controlado.

Estados de reserva: `held → settled/released/expired_review`. La expiración no libera automáticamente una reserva si la inferencia pudo haber terminado y no se conoce el resultado. Las reservas huérfanas pasan a revisión/reconciliación.

Los periodos de cuota guardan UTC de inicio/fin y la zona horaria IANA que originó el calendario. El periodo diario y mensual se calcula desde la zona horaria comercial configurada en la versión de plan o titular, con DST probado. No usar el huso del servidor implícitamente.

### 3.5 Créditos y libro inmutable

| Tabla | Responsabilidad |
|---|---|
| `billing_credit_accounts` | Cuenta por usuario y categoría |
| `billing_credit_lots` | Lote concedido/comprado con origen, expiración y saldo disponible/reservado |
| `billing_credit_ledger` | Eventos inmutables de concesión, reserva, consumo, liberación, expiración, compra y reverso |
| `billing_reservation_allocations` | Enlace de reserva a cada lote utilizado |

La migración 008 bloquea UPDATE, DELETE y TRUNCATE de `billing_credit_ledger`; no permitir modificaciones de entradas contables ordinarias. Correcciones se representan con entradas compensatorias vinculadas al movimiento original. El saldo disponible y reservado se actualiza dentro de la misma transacción que inserta el movimiento; una reconciliación puede reconstruir/verificar las proyecciones desde el ledger.

El orden de consumo debe estar versionado y ser determinista: por ejemplo, créditos gratuitos con expiración próxima, créditos incluidos en suscripción y créditos comprados, o la prioridad final que se apruebe. No asumir que la cuota de plan y los créditos comprados se suman o sustituyen: la política debe expresarlo de forma explícita y versionada.

No transferencias, no saldo negativo, ni acreditación por respuesta del frontend.

### 3.6 Pagos y eventos de proveedor

| Tabla | Responsabilidad |
|---|---|
| `billing_orders` | Orden interna con usuario, producto/plan, importe, moneda y estado |
| `billing_payment_attempts` | Intento en proveedor, UUID externo y referencia interna |
| `billing_provider_events` | Webhooks recibidos, firma validada, hash del cuerpo, timestamp y estado de procesamiento |
| `billing_payment_ledger_links` | Vínculo entre pago conciliado y concesión de crédito/suscripción |

Para QvaPay:
1. Crear orden interna y persistirla antes de solicitar factura.
2. Guardar la asociación `remote_id ↔ transaction_uuid`.
3. Verificar HMAC-SHA256 sobre los bytes originales del webhook y validar timestamp.
4. No acreditar desde redirección del navegador.
5. Consultar la transacción desde backend y comparar UUID, remote_id, importe, moneda y estado `paid`.
6. En una transacción PostgreSQL, registrar evento procesado, marcar orden pagada y conceder el lote/plan con clave única.
7. Repeticiones del mismo UUID devuelven resultado idempotente; una misma clave con datos contradictorios se pone en cuarentena.

La aprobación comercial de QvaPay comunicada por el propietario se conserva como `APPROVED`; la integración técnica sigue pendiente. No se realizan cobros reales en esta fase.

### 3.7 Costes de infraestructura y rentabilidad

| Tabla | Responsabilidad |
|---|---|
| `billing_cost_sources` | VPS, almacenamiento, GPU externa, API, electricidad u otro origen |
| `billing_cost_entries` | Factura/medición real, periodo, importe, moneda, evidencia y clasificación fija/variable |
| `billing_cost_allocations` | Método de asignación variable o fija por periodo/servicio |

Un coste sin factura o medición queda `unverified` y no entra como coste real confirmado. Los costes fijos se registran una vez por periodo. El reparto fijo por usuario se presenta como asignación analítica separada y nunca se suma otra vez al total contable.

### 3.8 Auditoría administrativa

Una tabla económica de auditoría debe guardar actor, acción, entidad, identificador, timestamp, motivo, correlación, valores anterior/nuevo redactados de secretos y hash encadenado o mecanismo equivalente. Acceso de solo append para aplicación; los cambios de tarifas, plan, excepciones, ajustes y suspensiones requieren rol global y motivo.

## 4. Flujo transaccional de una inferencia

1. Validar sesión y CSRF; resolver usuario y pertenencia al proyecto.
2. Validar idempotency key y payload hash. Si la petición ya existe, devolver su estado/resultado sin repetir la inferencia.
3. Resolver plan activo, versión de plan, excepciones, modelo permitido, límites de contexto y máximo de salida.
4. Abrir transacción PostgreSQL; bloquear filas de cuota y lotes de crédito en orden determinista para evitar deadlocks.
5. Comprobar cuota diaria/mensual, RPM, concurrencia y saldo disponible.
6. Crear request y reserva, reservar capacidad/cuota y asignar lotes de crédito. Confirmar transacción.
7. Llamar al adaptador de inferencia fuera de la transacción DB. Nunca mantener locks DB durante una inferencia lenta.
8. Guardar el resultado y sus contadores reales/estimados.
9. Abrir transacción de conciliación: bloquear reserva/counters/lotes; liberar exceso no utilizado; consumir cantidad real; ajustar cuotas y ledger; registrar coste/tarifa snapshot; marcar request reconciliada.
10. Si no se puede conocer el resultado, marcar `unknown` y conservar reserva para reconciliador; no liberar por timeout de cliente sin comprobar estado del motor.

La operación de conciliación es idempotente mediante UNIQUE(request_id, settlement_kind) y transición condicional desde estados permitidos. Dos workers pueden competir, pero solo uno puede cerrar la petición.

## 4.1 Cota de reserva previa para ATOMIC CODE (prototipo no conectado)

Se añadió `api/billing_budget.py` como cálculo puro y verificable de una cota previa. Para el runtime fijado `atomic-code:16k-8k`, la política reconoce únicamente el contrato de tokenizer Qwen byte-fallback. La cantidad de bytes UTF-8 del contenido completo es una cota superior conservadora de tokens de contenido para ese contrato; se suman 32 tokens por mensaje y 256 de overhead fijo de plantilla como margen explícito y versionado.

La función recibe la lista FINAL que se enviaría a Ollama, después de incorporar instrucciones del sistema, historial y RAG. Reserva también el máximo `num_predict` solicitado. Rechaza antes de inferencia si la cota input + output supera `num_ctx`, si el runtime no coincide exactamente o si el contrato de tokenizer no está soportado. La reserva en créditos aplica los ponderadores versionados a ambas cotas.

**Límites y condición de activación:**
- Es una cota conservadora para el contrato Qwen byte-fallback, no un tokenizer ejecutable ni una medición de uso real.
- La identificación del tag Ollama no demuestra por sí sola que su contenido no haya sido sustituido. Antes de activar cobro hay que verificar el digest/Modelfile/tokenizer del artefacto desplegado y fijar ese digest en el catálogo de modelo.
- Los 32 tokens por mensaje y 256 de plantilla son márgenes de seguridad configurables; deben contrastarse con la plantilla real del artefacto. No disminuirlos sin evidencia y pruebas.
- El valor devuelto todavía NO se pasa a `reserve_credits`, no se crea reserva y no se llama desde la ruta HTTP. Shadow Usage sigue sin cargos.
- La siguiente integración deberá calcular esta cota sobre los mensajes finales, persistir la reserva de forma atómica y solo después llamar a Ollama. Cualquier error o incertidumbre antes de la inferencia debe impedir la llamada.

## 5. Concurrencia y límites

- PostgreSQL es autoridad: `SELECT ... FOR UPDATE` sobre filas de cuota/lotes y actualizaciones condicionales con saldo suficiente.
- Bloquear siempre en orden estable (account → quota periods ordenados → credit lots por expiración/id) para reducir deadlocks.
- RPM se puede aproximar con ventanas persistidas o un limitador auxiliar; el control definitivo de gasto/concurrencia debe reconciliarse en PostgreSQL.
- Slots concurrentes deben tener lease con owner/request, expiración y recuperación. Un slot vencido no implica que una inferencia remota haya terminado.
- Reintentos de transacción solo para errores transitorios identificados y con idempotencia; nunca reintentar automáticamente una llamada de inferencia cuyo resultado sea incierto.

## 6. Errores, cancelaciones y streaming

- Fallo antes de enviar al motor: liberar toda la reserva.
- Error confirmado del motor sin generación: liberar tokens reservados y registrar coste cero de inferencia, conservando costes de infraestructura medidos por separado.
- Respuesta parcial con tokens reales: reconciliar únicamente uso confirmado y marcar `partial`.
- Timeout/desconexión sin resultado verificable: `unknown`, mantener reserva y abrir reconciliación; no asumir consumo cero.
- Streaming no se habilita en esta fase. Cuando exista, cada evento de token/chunk necesita acumulación segura y finalización idempotente; desconexión del cliente no debe saltarse la conciliación.

## 7. Seguridad y privacidad

- No aceptar del cliente usuario, plan, coste, tokens, precio, balance, reviewer o privilegios como fuente de verdad.
- Separar `billing_admin`, `billing_support` y lectura de reportes; acceso mínimo y MFA/2FA para acciones críticas cuando el sistema de identidad lo soporte.
- No conceder administración global a roles de proyecto.
- Proteger webhooks contra replay, firma incorrecta, timestamps antiguos y eventos duplicados.
- No registrar prompts/respuestas completos en ledger económico; usar IDs, hash opcional y metadatos mínimos.
- Retención, exportación, eliminación y anonimización deben respetar obligaciones contables y privacidad; definir política antes de producción.
- La API heredada global permanece fuera del billing individual hasta autenticación propia.

## 8. Migraciones

Las migraciones comerciales serán nuevas (por ejemplo, siguientes números libres después de 005), estrictamente aditivas, con constraints e índices revisados. No editar migraciones ya aplicadas. El migrador actual `api/migrate.py` registra checksum, toma advisory lock PostgreSQL y ejecuta cada archivo en transacción; un checksum distinto en una migración aplicada aborta.

Cada migración nueva necesita:
- prueba de descubrimiento y checksum;
- prueba de aplicación en PostgreSQL de CI o entorno efímero compatible;
- prueba de rollback documentada si existe operación inversa segura;
- validación de constraints y claves foráneas;
- revisión de impacto de locks y tamaño de tablas;
- ningún paso destructivo ni migración automática en arranque.

No ejecutar migraciones reales en VPS como parte de esta fase.

## 8.1 Auditoría de rollback y política de reversión

La carpeta `migrations/rollback/` contiene actualmente:

- `002_down.sql`: elimina `project_memories`, `rag_chunks` y `rag_files`, y borra la versión 002 de `schema_migrations`. Su propio encabezado advierte que es destructiva.
- `003_down.sql`: elimina `audit_chain_head`, `audit_log` y `action_approvals`, y borra la versión 003 de `schema_migrations`. También es destructiva.
- No se identificaron scripts down para 001, 004 ni 005.

**Conclusión:** estos scripts no son rollback seguro para producción. Su ejecución podría destruir memoria RAG, aprobaciones y registros de auditoría. No deben ejecutarse como rutina de despliegue ni usarse para revertir migraciones comerciales. Para billing se priorizarán migraciones aditivas y correcciones forward-only; cualquier rollback de esquema deberá demostrar que no elimina datos económicos. Los movimientos contables nunca se revierten borrándolos: se usan asientos compensatorios.

El migrador `api/migrate.py` confirma checksum, lock consultivo PostgreSQL y transacción por migración. El lock se libera en `finally`; el archivo de migración aplicado no se debe editar. No se ejecutó el migrador ni ningún script down.

## 8.2 Contrato de inferencia y modo de observación

La lectura de `api/ollama.py`, `api/workspace_routes.py`, `api/schemas.py` y `api/main.py` confirma:

- `chat_with_usage()` devuelve un `InferenceResult` tipado con texto, modelo solicitado/devuelto, contadores y duraciones; el wrapper `chat()` conserva compatibilidad y devuelve solo `message.content`.
- La ruta autenticada `/workspace/chat/completions` compone un system prompt del servidor con contexto RAG antes de llamar a Ollama.
- El esquema del cliente solo admite mensajes `user/assistant`; el cliente no puede suministrar el system prompt.
- El campo `model` del request no selecciona el motor. El adaptador usa `settings.chat_model`; la respuesta actual informa el modelo configurado, no verifica el campo `model` devuelto por Ollama.
- La API heredada `/v1/chat/completions` usa una API key compartida, no identifica un usuario económico y queda excluida de billing individual mientras no exista identidad individual verificable.
- Streaming no está implementado y debe permanecer deshabilitado.

### Resultado tipado implementado en Shadow Mode

El adaptador debe evolucionar de devolver un string a devolver un objeto inmutable equivalente a:

```python
InferenceResult(
    content: str,
    requested_model: str,
    returned_model: str | None,
    done: bool | None,
    prompt_eval_count: int | None,
    eval_count: int | None,
    total_duration_ns: int | None,
    load_duration_ns: int | None,
    prompt_eval_duration_ns: int | None,
    eval_duration_ns: int | None,
    usage_source: Literal["ollama_response", "unavailable"],
)
```

Validaciones obligatorias: contadores enteros no negativos; no convertir campos ausentes en cero; registrar requested_model y returned_model por separado; duración en unidad explícita; no registrar prompt ni respuesta en telemetría económica. El endpoint seguirá devolviendo el mismo contrato público de chat, añadiendo solo metadatos no sensibles si se aprueba expresamente.

### Qué cuenta como input

El input facturable debe corresponder al prompt que realmente recibe el motor, incluyendo system prompt de AXION, historial enviado, contexto RAG y cualquier mensaje/herramienta incorporado antes de la inferencia. La fuente primaria es `prompt_eval_count` de Ollama; no se deben sumar manualmente las longitudes de mensajes porque eso duplicaría/estimaría tokens. El output primario es `eval_count`.

### Primera fase de código: Shadow Mode publicada

La primera implementación está publicada en `main` y mantiene el comportamiento económico sin cambios:
1. `api/ollama.py` define `InferenceResult` y `chat_with_usage()` para conservar contadores y duraciones de Ollama.
2. La función `chat()` sigue devolviendo texto para compatibilidad con consumidores existentes.
3. La ruta autenticada `/workspace/chat/completions` usa el resultado tipado y emite un evento JSON con identidad, proyecto, modelos, contadores y duraciones.
4. El evento no incluye prompts ni respuestas; la respuesta pública del endpoint conserva su estructura.
5. La ruta heredada `/v1` permanece fuera de medición individual.
6. Los contadores inválidos o ausentes quedan como `None`; no se inventan valores ni se realiza cobro.

Las pruebas añadidas cubren parsing, payload HTTP no streaming, timeout, wrapper de compatibilidad y contrato HTTP de workspace. **La ejecución de pytest y CI sigue pendiente de confirmación.**

Shadow Mode no crea registros persistentes en PostgreSQL, saldos, créditos, reservas, cuotas ni costes. La telemetría de logs no es un libro contable ni puede utilizarse para cobrar.

## 9. Orden recomendado de construcción

1. Contratos y adaptador de inferencia tipado con metadatos de uso (sin facturar).
2. Esquema de peticiones, mediciones y tarifas versionadas.
3. Motor de cuotas/reservas sin pagos.
4. Ledger de créditos y pruebas de atomicidad.
5. Integración de suscripciones y órdenes.
6. Adaptador QvaPay y webhooks conciliados en sandbox oficial.
7. RBAC global y auditoría administrativa.
8. API de consumo/historial para el usuario.
9. Costes de infraestructura y reportes de rentabilidad.
10. UI de usuario/admin después de que APIs estén probadas.

## 10. Decisiones de política autorizadas por el propietario

**Estado:** decisiones aprobadas para orientar la primera implementación. El propietario autorizó expresamente al equipo a resolver las seis decisiones pendientes. Se adoptan las reglas siguientes como valores iniciales versionados y editables por administración autorizada; no son todavía precios activos ni habilitan cobros.

| # | Decisión | Regla inicial aprobada |
|---|---|---|
| 1 | Prioridad de consumo | Primero cuota gratuita diaria vigente; después cuota incluida en la suscripción; por último créditos comprados, de los lotes con vencimiento más próximo (FEFO). El orden se guarda en la versión de política y puede configurarse por plan. |
| 2 | Caducidad | Cuotas gratuitas diarias expiran al cierre de su ventana. Cuota/bolsa incluida en suscripción expira al final del ciclo y no se acumula inicialmente. Créditos comprados no expiran durante los primeros 12 meses desde la compra; al cumplirse ese plazo pasan a vencimiento, sujeto a que la política legal/comercial aplicable lo permita. No se activarán ventas hasta revisar términos y requisitos de reembolso/expiración. |
| 3 | Zona horaria | UTC como zona horaria comercial inicial y predeterminada para reset diario y periodos mensuales. Guardar siempre zona IANA y límites UTC exactos de cada periodo. La arquitectura permitirá zona horaria por usuario cuando exista una preferencia explícita y se prueben cambios/DST; nunca usar el huso del servidor. |
| 4 | Sobreconsumo | Al agotar la cuota incluida, permitir continuar solo si el usuario tiene créditos comprados disponibles y la política de su plan permite expresamente ese fallback. No generar deuda ni saldo negativo. El comportamiento predeterminado será rechazar con error de cuota agotada cuando no haya créditos comprados suficientes. |
| 5 | Conversión y modelos | Mantener 1 crédito por token contabilizado como unidad interna de consumo, pero aplicar ponderadores configurables por modelo y por tipo de token (input/output) para que el coste comercial no sea idéntico entre modelos si sus tarifas difieren. Para Atomic Code, los valores iniciales de simulación serán 1 crédito/token input y 1 crédito/token output hasta que se aprueben tarifas comerciales; otros modelos no heredan automáticamente esa tarifa. Guardar siempre la versión de ponderadores aplicada. |
| 6 | Titularidad | Primera versión individual por `user_id`; `project_id` solo atribuye uso. Organizaciones y saldos compartidos quedan para una fase posterior, sin simular organizaciones ni migrar titulares. |

### Reglas complementarias para evitar ambigüedades

- **Cuota y créditos son dos fuentes distintas:** la cuota incluida se consume primero; los créditos comprados solo cubren el exceso permitido. No se convierte automáticamente la cuota no usada en créditos.
- **Créditos gratuitos:** se conceden como lotes separados, con vencimiento diario y sin transferibilidad. La cuota FREE diaria propuesta no se duplica como otro lote gratuito; se registra como entitlement/cuota para evitar doble contabilización.
- **Créditos de suscripción:** se mantienen separados de los créditos comprados. En la primera versión la asignación incluida se limita por periodo y vence al cierre del ciclo; no se acumula ni se reembolsa como efectivo.
- **Créditos comprados:** no se consumen antes de cuotas incluidas. Se consumen FEFO entre lotes comprados. Los reembolsos se registran mediante movimientos compensatorios y solo si el estado de consumo permite el ajuste.
- **Tokens:** input y output se registran separadamente. El total de consumo es input + output; el coste y los créditos pueden usar ponderadores diferentes por modelo. Tokens de historial, system prompt, herramientas y RAG que efectivamente entren al contexto del motor forman parte de input cuando el motor los cuenta. No se debe facturar contenido rechazado antes de inferencia.
- **Conteo no disponible:** no convertir NULL en cero ni emitir cobro definitivo estimado sin política visible. Mantener reserva y marcar conciliación pendiente hasta recuperar contador o aplicar un fallback estimado explícitamente permitido y auditado.
- **Planes y precios:** los importes y límites del roadmap siguen siendo valores de referencia. Deben publicarse como versiones de plan/tarifa después de pruebas, revisión de costes y aprobación comercial; no se hardcodean ni se activan por defecto.
- **Cambios de política:** toda modificación crea una nueva versión con fecha efectiva. Una solicitud conserva la versión de plan, ponderadores y tarifas que tenía al reservarse.

## 11. Criterios de aceptación de Fase 2

- Diagrama lógico de entidades y relaciones aprobado.
- Semántica exacta de estados e idempotencia documentada.
- Fórmula de reservas y conciliación definida para éxito, fallo, parcial y resultado desconocido.
- Reglas de prioridad/expiración de créditos decididas y versionables.
- Ventanas de cuota y zona horaria decididas, con UTC como predeterminado.
- Modelo de administración global definido y separado de roles de proyecto.
- Contrato QvaPay alineado con el documento de integración, sin secretos.
- Plan de pruebas y migraciones PostgreSQL definido.
- Ningún pago, cobro, crédito o migración activado por este documento.

**Estado de salida:** diseño técnico actualizado con las decisiones iniciales autorizadas; implementación económica aún no iniciada.

## 12. Diseño separado de persistencia Shadow Mode

La persistencia Shadow Mode está implementada parcialmente mediante migración 006 y escritura best-effort, sin facturación. No activa cuotas, reservas, ledger ni cobros. Las pruebas PostgreSQL de CI deben pasar antes de cualquier despliegue.
