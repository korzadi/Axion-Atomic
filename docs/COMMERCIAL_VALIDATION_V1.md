# Validación comercial AXYRON ATOMIC V1.0 — rama `agent/opencode-vps`

**Fecha:** 2026-11-08 · **SHA de trabajo:** el commit que incluye este documento · **Entregables:** A–H de la especificación comercial aprobada.

> **Estado:** validación técnica de alta visibilidad, **no** certificación de rentabilidad. Los cobros permanecen **desactivados** (`BILLING_ENFORCEMENT_ENABLED=false`, `QVAPAY_ENABLED=false`, catálogo `preview_only`). Ninguna cifra de este documento es un coste medido en USD salvo que se indique lo contrario; los valores procedentes del roadmap interno se marcan como **referencia provisional, no medida**. No se ha cambiado el catálogo aprobado, ni los precios, ni la configuración, ni el VPS.

---

## A. Auditoría del sistema de facturación actual

### Estado real del código (verificado en este árbol)

| Componente | Archivo | Estado |
|---|---|---|
| Órdenes de pago internas | `api/payment_manager.py` + migración 016 | Implementado: estados `pending/under_review/paid/expired/cancelled/refunded`, eventos append-only, idempotencia por `provider_transaction_id` |
| Persistencia de invoices Lightning | `api/qvapay_settlement.py` + migración 023 | Implementado: una invoice abierta por orden, supersede, referencia LNURL unguessable |
| Conciliación paginada | `api/qvapay_settlement.py::reconcile_lightning_payments` | Implementado: referencia + sats exactos + destinatario; acredita vía `confirm_verified_payment` (verificación server-side, en la misma transacción, una sola vez) |
| Expiración de órdenes | `expire_overdue_orders` (en `api/payment_manager.py`) | Implementado: órdenes vencidas → `expired`, invoice abierta → `expired`, evento idempotente |
| Medición de tokens real | `api/ollama.py::InferenceResult` (`prompt_eval_count`, `eval_count`, duraciones) | Implementado y **consumido en producción sombra**; `usage_source='unavailable'` cuando el proveedor no reporta contadores |
| Eventos de uso shadow | `inference_usage_events` (migración 006) | Implementado; agregados por modelo expuestos en `/admin/billing/overview` (`usage`) |
| Reservas, ledger, allocation | `api/billing_reservations.py`, `api/billing_policy.py`, migraciones 007–010 | Implementado y probado con dobles y PostgreSQL desechable (70 pruebas en CI) |
| Ledger inmutable y reversos auditados | `reverse_settled_reservation` + `/admin/billing/reservations/reverse` | Implementado; 10 contratos HTTP + 3 pruebas PostgreSQL |
| Recuperación de liquidaciones | `api/billing_recovery.py` + `/admin/billing/executions/recover` | Implementado; reintenta liquidación sin repetir inferencia |
| Preflight de coste/tokenización | `api/billing_budget.py`, `api/billing_preflight.py` | Implementado; aborta si no hay digest/plantilla verificados |
| Créditos de inferencia | `credits_for_usage` (`billing_input_credit_weight=1`, `output_credit_weight=1`) | **1 crédito = 1 token contabilizado** (entrada y salida con mismo peso) |
| Catálogo comercial | `api/commercial_catalog.py` | Deliberadamente `preview_only`: sin planes, paquetes ni precios publicados |
| Checkout / acreditación | No implementado | Deshabilitado hasta catálogo aprobado, precios cargados en BD, sandbox oficial y verificaciones de esta validación |

### Verificación de la medición real de consumo por modelo

- El path de chat (`workspace_chat` → `chat_with_usage`) envía `stream=false` y registra `prompt_eval_count`/`eval_count` cuando Ollama los reporta.
- En esta sesión se ejecutó el runner real de medición (`scripts/measure_model_tokens.py`, 2026-11-08, host `agent/opencode-vps`, Ollama privado en `172.16.0.1:11434`, modelo `atomic-code:1.1` = 7.62B Q4_K_M):
  - Prompt corto (18 tokens): **18 entrada / 41 salida**; carga del modelo 196 s (frío), evaluación ~4.1 s.
  - Prompt medio (26 tokens): **26 entrada / 96 salida**; evaluación ~9.3 s (~10.3 tok/s salida; prompt eval ~28 tok/s).
  - Embedding `nomic-embed-text:latest`: respondió vector de 768 dims en ~5.2 s (incluye carga del modelo).
- Los contadores medidos confirman que el pipeline registra consumo real por solicitud; la atribución por usuario solo ocurre en modo sombra (`inference_usage_events`) y no bloquea cobros todavía.

### Brecha estructural detectada (crítica para el modelo comercial)

**La semántica de crédito 1:1 (1 crédito = 1 token) es incompatible con el catálogo aprobado.** Con los pesos actuales:
- El plan FREE (50 créditos) ≈ **una respuesta de medio turno**; STARTER (300 créditos) ≈ **2,4 respuestas medias al mes** por 4,99 USD. El catálogo tiene sentido comercial solo si 1 crédito ≈ 100 tokens o similar.
- Cambiar la ponderación de créditos es un cambio funcional, no cosmético: afecta a `billing_input/output_credit_weight`, a los importes ya almacenados en lotes y ledger, y a las conversiones históricas. **No se ha cambiado nada; requiere decisión del propietario.**

---

## B. Matriz de costes por modelo y operación

**Advertencia metodológica.** El coste por token **no está medido en USD**: no existe amortización atribuible del host (CPU VPS), energía, almacenamiento ni red por solicitud; Qdrant Cloud y los servicios externos no tienen tarifas atribuidas por usuario en el código. Lo que sí está medido/derivado de forma reproducible son los **contadores de tokens y tiempos** de la inferencia local. Las cifras USD de la tabla provienen de las **tarifas internas provisionales del roadmap interno** (marcadas «provisional, no medida») y sirven únicamente como simulación de sensibilidad.

| Operación | Tokens medidos/estimados | Base | Coste variable USD (provisional, no medido) |
|---|---|---|---|
| Chat corto (1 turno) | 18 entrada / 41 salida (medido) | `atomic-code:1.1` | $0,006 entrada + $0,012 salida ≈ **$0,018** |
| Chat medio (1 turno) | 26 entrada / 96 salida (medido) | idem | $0,008 + $0,029 ≈ **$0,037** |
| Chat con historial (sesión de 10 turnos, contexto ~2.000 tk) | ~2.000 entrada / ~1.000 salida (estimado por la implementación: historial reenviado completo) | idem | $0,600 + $0,300 ≈ **$0,90** |
| Respuesta limitada por `max_tokens` | depende del techo; presupuesto acotado por `billing_preflight` | idem | acotado con techo configurable |
| Ingestión RAG (1 documento medio, ~600 tokens + 1 embedding × 5 chunks) | ~600 entrada (embed, **no** genera salida) | `nomic-embed-text` | sin tarifa de embedding publicada en roadmap; tiempo medido ≈ s/request |
| Consulta RAG (contexto + respuesta) | ~800 entrada / ~200 salida (estimado) | ambos modelos | $0,240 + $0,060 ≈ **$0,30** |
| Ejecución de agente (propuesta de cambio, con aprobación) | variable por tarea; sin medición agregada publicada | `atomic-code:1.1` | pendiente de instrumentación agregada |

Notas:
- El modo sombra contabiliza `inference_usage_events` por solicitud con `requested_model`/`returned_model`, listo para poblar esta tabla con datos reales antes de cualquier cobro.
- Coste de **infraestructura** (VPS, backup, Qdrant Cloud, Redis, volúmenes, GPU externa si se usara): **sin atribución por usuario ni medición de $/solicitud en el repositorio**. Se trata como coste fijo mensual y se parametriza por separado; no se inventa un reparto.

---

## C. Simulación económica por plan

Comisión de pago asumida para la simulación: **0,5 %** (Lightning Address, según pantalla compartida por el propietario el 2026-11-08). Sensibilidad evaluada con 1 % y 2,5 %. **Comisión no confirmada por escrito por QvaPay; usar solo como hipótesis.**

Ingreso neto = precio × (1 − comisión). Coste variable máximo admisible = neto × 0,65 (margen ≥ 35 %).

| Plan | Precio/mes | Créditos/mes | Neto @0,5 % | Coste var. máx ($) | **Máx $/crédito** | Precio/crédito |
|---|---:|---:|---:|---:|---:|---:|
| FREE | $0,00 | 50 (una vez) | $0,00 | $0,000 | $0,000 | — |
| STARTER | $4,99 | 300 | $4,965 | $3,227 | **$0,01076** | $0,01663 |
| PLUS | $9,99 | 750 | $9,940 | $6,461 | **$0,00861** | $0,01332 |
| PRO | $19,99 | 1.700 | $19,890 | $12,929 | **$0,00761** | $0,01176 |
| STUDIO | $39,99 | 3.600 | $39,790 | $25,864 | **$0,00718** | $0,01111 |

| Paquete | Precio | Créditos | Neto @0,5 % | Coste var. máx ($) | **Máx $/crédito** | Precio/crédito |
|---|---:|---:|---:|---:|---:|---:|
| 100 c | $1,99 | 100 | $1,980 | $1,287 | **$0,01287** | $0,01990 |
| 250 c | $4,49 | 250 | $4,468 | $2,904 | **$0,01162** | $0,01796 |
| 600 c | $9,99 | 600 | $9,940 | $6,461 | **$0,01077** | $0,01665 |
| 1.500 c | $19,99 | 1.500 | $19,890 | $12,929 | **$0,00862** | $0,01333 |
| 4.000 c | $44,99 | 4.000 | $44,765 | $29,097 | **$0,00727** | $0,01125 |

Sensibilidad de la columna **máx $/crédito**:

| Plan | @0,5 % | @1 % | @2,5 % |
|---|---|---|---|
| STARTER | 0,01076 | 0,01070 | 0,01054 |
| PLUS | 0,00861 | 0,00857 | 0,00844 |
| PRO | 0,00761 | 0,00757 | 0,00745 |
| STUDIO | 0,00718 | 0,00715 | 0,00704 |

**Lectura:** el margen del 35 % se cumple para cualquier plan/paquete mientras el coste variable real por crédito sea inferior al umbral. Las suscripciones grandes (PRO, STUDIO) tienen menos holgura por crédito que los paquetes pequeños. **Los planes no incumplen por construcción de precio: el riesgo reside en que el consumo real supere la asignación y consuma del fondo (rebaja), en que el coste marginal del modelo local supere el umbral, o en que la semántica de crédito cambie (ver hallazgo crítico).**

Ejemplo ilustrativo con la medición de este host (coste de inferencia local despreciable en USD en hardware propio): incluso sirviendo el 100 % de las asignaciones, el coste variable directo de guardar las cuotas mensuales es marginal; el coste significativo sería el cómputo atribuible (no medido). **Esto no certifica rentabilidad; indica que el precio soporta amplio margen si el coste atribuible por token es bajo, como es esperable en self-hosting a escala pequeña.**

---

## D. Presupuesto de adquisición mediante créditos gratuitos

- FREE = 50 créditos por cuenta verificada, una sola concesión inicial (según política aprobada; `create_payment_order`/grant path ya soportan concesiones auditadas vía ledger).
- Con semántica 1:1 (actual): presupuesto por cuenta = 50 créditos ≈ 50 tokens ≈ **$0,00–0,002** de inferencia local; irrelevante pero inútil para el usuario (menos de un turno).
- Con concesión única y peso 1:100 (propuesta del apartado H): 50 créditos = 5.000 tokens ≈ 40 turnos medios/mes ≈ coste marginal despreciable (<$0,01) por cuenta.
- **Riesgo de abuso:** creación masiva de cuentas para acumular 50× N créditos. Mitigación existente: registro con verificación de correo + rate limiting por IP (`api/rate_limit.py`, migración 013) y consentimiento legal (migración 015). Falta: límite de concesiones por IP/dispositivo/teléfono y detección de patrones; se documenta como pendiente.
- **Contabilidad:** la concesión inicial debe registrarse como asiento de ledger `grant` con referencia única por usuario (análoga a `payment-grant:{order_id}`), p. ej. `free-grant:{user_id}`, para impedir dobles concesiones y permitir auditoría. Verificado que el ledger admite grants; no hay doble vía de concesión hoy.
- Sin verificación de titularidad de saldos (Stripe-like) en Lightning: los pagos son finales; los créditos gratuitos no son reembolsables por naturaleza.

---

## E. Análisis de sensibilidad de utilización

Escenarios con la ponderación propuesta de crédito = 100 tokens (a modo ilustrativo) y usuario tipo de 122 tokens/respuesta media:

| Plan | Cobertura tokens @100 % asignación | @30 % uso | @60 % uso | @100 % uso |
|---|---:|---:|---:|---:|
| FREE | 5.000 | 1.500 | 3.000 | 5.000 |
| STARTER | 30.000 | 9.000 | 18.000 | 30.000 |
| PLUS | 75.000 | 22.500 | 45.000 | 75.000 |
| PRO | 170.000 | 51.000 | 102.000 | 170.000 |
| STUDIO | 360.000 | 108.000 | 216.000 | 360.000 |

En **coste variable** (usando las tarifas provisionales del §B como hipótesis no medida), el uso al 100 % consume:

| Plan | Tokens @100 % | Coste variable hipotético (ref. provisional) | Neto disponible | Margen bruto hipotético |
|---|---:|---:|---:|---:|
| STARTER | 30.000 | ~$0,90 | $4,97 | ~82 % |
| PLUS | 75.000 | ~$2,25 | $9,94 | ~77 % |
| PRO | 170.000 | ~$5,10 | $19,89 | ~74 % |
| STUDIO | 360.000 | ~$10,80 | $39,79 | ~73 % |

Incluso con utilización máxima al precio de inferencia provisional, los planes mantienen >35 % de margen. **Si el coste real atribuible por token del self-hosting es ≥10× la referencia provisional, STARTER incumpliría el margen; ya entonces la absorción sería la correcta vía límite/peso, no subida de precio (ver H).**

Paquetes: márgenes por unidad superiores a suscripciones equivalentes y agotaje solo por consumo efectivo; no hay riesgo de «usuarios que pagan y no usan» ni de «usuarios que usan todo» (se detiene en el agotamiento de créditos, con `InsufficientCredits` y sin saldo negativo).

---

## F. Riesgos de pérdidas

| # | Riesgo | Probabilidad | Impacto | Control existente | Recomendación |
|---|---|---|---|---|---|
| 1 | **Semántica de crédito incoherente** (1:1 con cuotas comerciales) | Alta | Crítico: cuotas inservibles | Ninguno (configuración actual) | Ponderar créditos (propuesta H) **antes** de publicar; decisión del propietario |
| 2 | **Coste de cómputo no atribuido** por usuario/solicitud | Media | Alto; margen real desconocido | Métricas de uso en sombra | Atribuir VPS/GPU/Qdrant por usuario en telemetría interna; reportar mensualmente |
| 3 | **Gratuito multiplicado** (cuentas falsas) | Media | Bajo–Medio | Verificación correo + rate limit IP | Límite de concesiones por huella/teléfono/pago previo |
| 4 | **Reserva retenida** sin liquidación (`unknown`) | Media | Medio: créditos bloqueados | `unknown/review` + recuperación administrativa (`billing_recovery`) | Alertas cuando `recovery_due` > umbral |
| 5 | **Consumo dúplice por usuario** (pid/editor/agente) | Baja | Medio | Idempotencia por `request_id` + `entitlement` | Aceptación E2E antes de habilitar cobro |
| 6 | **Pago recibido pero no acreditado** (caída entre webhook y grant) | Baja | Alto reputacional | Reconciliación paginada implementada y idempotente | Job programado + métrica «órdenes pagadas sin lot» |
| 7 | **Pagos tardíos/denegados** (Lightning confirmación diferida) | Media | Bajo | Confirmación retiene solo tras verificación | Estados `under_review` y `payment_observed` sin acreditar |
| 8 | **Comisión Lightning imprevisible** (0,5 % mostrado, no contractual) | Media | Bajo–Medio | Sensibilidad 1 % y 2,5 % evaluada | Confirmar tarifa oficial por escrito; recalcular netos |
| 9 | **Reembolsos sin reversibilidad en Lightning** (pago final) | Media | Medio | Ledger con reversos compensatorios | Política de reembolso en créditos, no en sats |
| 10 | **STUDIO explotado por antiabuso** (abuso de agente) | Media | Medio | Autorización por proyecto; no ejecuta sin aprobación | Cuota mecánica por usuario/proyecto/día |
| 11 | **Cambio de tarifa de Ollama/modelo mayor** (más coste por token) | Baja | Medio | Solo `atomic-code:1.1` medido | Versionar tarifas; re-simular por versión de modelo |
| 12 | **STUDIO con descuento efectivo** vs paquetes | Baja | Bajo (comercial) | 1.700 PRO vs 1.500 pkg $19,99 | Revisar? **sin cambiar catálogo** |
| 13 | **Uso de FREE sin conversion** | Alta | No aplica (coste marginal ≈ 0) | — | Métrica de conversión free→paid |
| 14 | **Pérdida/fuga de ledger** | Muy baja | Crítico | Ledger append-only + transacciones + CI | Backup regular + restore drill (DB-02 verificado) |

---

## G. Cumplimiento del margen mínimo del 35 %

**Condición medida:** el coste variable directo de inferencia local atribuible por crédito es órdenes de magnitud menor que el umbral máximo (§B: un turno medio ≈ $0,037 provisional = ~1/4 crédito a 1:100). **Ningún plan incumple el margen con las hipótesis actuales.**

**Condiciones para certificarlo:**
1. Ponderación de créditos aprobada y aplicada (sin saltos de conversión retroactivos no auditados).
2. Coste atribuible por token **medido** durante ≥30 días de sombra en producción (tokens, latencia, CPU) y asignado por usuario.
3. Comisión Lightning confirmada por escrito (herramienta oficial/list price).
4. Precios y cuotas cargados en base de datos con versión de tarifa; `billing_enforcement_enabled=true` solo tras checklist aparte.
5. Conciliación automática en verde (`/admin/billing/overview`: 0 invoices abiertas vencidas no expiradas, `overdue_open=0`).

**Conclusión honesta:** el catálogo aprobado es **consistente con un margen ≥35 %** bajo condiciones de coste local razonables y verificables; **no** es certificable como rentable sin las mediciones de coste real (§B) ni sin aplicar la ponderación de créditos coherente. **Los cobros permanecen desactivados.**

---

## H. Recomendaciones (sin modificar el catálogo aprobado)

1. **Semántica de créditos (decisión del propietario requerida):** adoptar peso 1 crédito = 100 tokens de entrada+salida (o equivalente) antes de publicar el catálogo; mantener la concesión FREE de 50 créditos. Alternativa: mantener 1:1 y recalcular cuotas — inutilizable en la práctica.
2. **Tarifas por modelo en BD:** persistir `model_rates` versionadas (input/output por 1M tokens) pobladas con costes atribuibles tras 1 mes de sombra; no usar las tarifas del roadmap como hechos.
3. **Cost attribution mensual:** tablero `/admin/billing/overview` extendido (ya expone `usage` por modelo; añadir coste estimado vs crédito consumido para cerrar el círculo).
4. **Comisión de pago:** solicitar confirmación escrita de la tarifa Lightning real; si >2 %, recalcular (tablas de sensibilidad ya en §C).
5. **Cobros:** mantener `preview_only` hasta: precios en BD, catálogo aprobado aplicado (migración + admin UI), verificación oficial QvaPay con credenciales-sandbox en entorno aislado, monitoreo ≥2 semanas de sombra, y release gate (`docs/PRODUCTION_INITIAL_RELEASE_GATE.md`) completo.
6. **Antiabuso FREE:** verificación de correo obligatoria (ya), límite de creación de cuentas por IP/dispositivo, y un único grant `free-grant:{user_id}` en ledger.
7. **Alertas:** `overdue_open > 0`, `recovery_due > 0`, reservas en `unknown` crecientes, grants free por encima de umbral/día.
8. **Reembolsos:** implementar flujo compensatorio en créditos (no sats; Lightning es final); auditoría en la misma transacción.
9. **STUDIO/PRO:** límites blandos por proyecto/día además de cuotas mensuales; el agente nunca ejecuta sin aprobación (ya), pero el coste de planes agentes es mayor — monitor de `agent_runs` por usuario.
10. **Documentación:** actualizar `docs/COMMERCIAL_TOKENS_CREDITS_ECONOMICS_ROADMAP.md` con este informe una vez aprobada la ponderación (no antes, para no institucionalizar números no acordados).
11. **No activar `BILLING_ENFORCEMENT_ENABLED` ni `QVAPAY_ENABLED` hasta la lista de verificación completa; el panel admin ya permite supervisar reservas, ledger, reversos y recuperación sin cobrar.**
12. **Datos pendientes antes de comercializar:** coste atribuible por usuario (CPU/RAM/GPU/Qdrant/almacenamiento), distribución real free/paid (solo estimaciones), tasa de comisión confirmada, política de reembolso, y tarifa por modelo mayor cuando cambie el modelo.

---

## Criterio de aceptación frente a la especificación

| Requisito | Estado |
|---|---|
| 1. Inspección existente | Hecho (§A) |
| 2. Reutilizar migraciones/componentes | Sin cambios en esquema/pago/ledger; solo tooling nuevo de lectura |
| 3. Verificar medición real | Hecho y reproducible (§A; runner incluido) |
| 4. Tabla de costes por operación | Hecha como hipótesis medida/estimada; USD real pendiente de atribución |
| 5. Tarifas basadas en datos medidos | Pendientes de atribución de costes (pendiente de 30 días de sombra) |
| 6. Presupuesto de créditos gratuitos | Hecho (§D) |
| 7. Simulación FREE→STUDIO | Hecha (§C, §E) |
| 8. Utilización baja/media/alta | Hecha (§E) |
| 9. Comisiones, reembolsos, ledger, duplicados | Documentados como hipótesis; reversos/completados ya operativos; duplicados por `UNIQUE` + idempotencia |
| 10. Informe de rentabilidad | Hecho con hipótesis explícitas (§C, §G); no certificación |
| 11. Incumplimientos de margen | Ningún plan incumple con hipótesis actuales; riesgo concentrado en la semántica de crédito y en el coste atribuible no medido |
| 12. Propuestas sin cambiar catálogo | Hechas (§H); catálogo intacto |

**Veredicto:** la especificación comercial queda **técnicamente validada con datos de mercado y laboratorio insuficientes** en dos aspectos: (1) coste atribuible real y (2) semántica de créditos. Mientras tanto: **cobros desactivados**. Ningún número de este informe autoriza por sí mismo activar `BILLING_ENFORCEMENT_ENABLED`.
