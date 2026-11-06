# Diseño técnico — economía, medición, cuotas y créditos de AXION ATOMIC

**Estado:** propuesta técnica para revisión; no implementada  
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

Las tablas son una propuesta lógica. Nombres y tipos finales se ajustarán a las convenciones del repositorio durante la implementación.

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

No permitir UPDATE/DELETE de entradas contables ordinarias. Correcciones se representan con entradas compensatorias vinculadas al movimiento original. El saldo disponible y reservado se actualiza dentro de la misma transacción que inserta el movimiento; una reconciliación puede reconstruir/verificar las proyecciones desde el ledger.

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

## 10. Preguntas de política que deben cerrarse antes de migrar

Estas decisiones no se pueden inferir del código actual:

1. ¿La cuota incluida en el plan se consume antes que los créditos comprados, o los créditos comprados tienen prioridad?
2. ¿Los créditos incluidos en suscripción caducan al renovar o se acumulan?
3. ¿La cuota FREE diaria se restablece por zona horaria local del usuario o por una zona horaria global del servicio?
4. Si la petición supera la cuota incluida, ¿se rechaza o se permite consumir créditos comprados?
5. ¿Se factura input y output con la misma unidad de crédito (1 crédito/token) para todos los modelos?
6. ¿Las suscripciones iniciales se vinculan al usuario individual o se necesita desde el inicio una cuenta de organización?

Hasta resolverlas, se pueden finalizar contratos y prototipos no persistentes, pero no conviene fijar constraints o migraciones irreversibles basadas en supuestos.

## 11. Criterios de aceptación de Fase 2

- Diagrama lógico de entidades y relaciones aprobado.
- Semántica exacta de estados e idempotencia documentada.
- Fórmula de reservas y conciliación definida para éxito, fallo, parcial y resultado desconocido.
- Reglas de prioridad/expiración de créditos decididas.
- Ventanas de cuota y zona horaria decididas.
- Modelo de administración global definido y separado de roles de proyecto.
- Contrato QvaPay alineado con el documento de integración, sin secretos.
- Plan de pruebas y migraciones PostgreSQL definido.
- Ningún pago, cobro, crédito o migración activado por este documento.

**Estado de salida:** diseño inicial preparado para revisión; implementación económica aún no iniciada.
