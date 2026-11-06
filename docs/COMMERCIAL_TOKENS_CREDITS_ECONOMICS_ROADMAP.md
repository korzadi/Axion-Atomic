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
