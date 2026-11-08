# QvaPay — método de cobro previsto para AXION ATOMIC

**Estado:** aprobación comercial de QvaPay confirmada; contrato oficial de Lightning Address confirmado y adaptador de cliente implementado. Persisten pendientes de producto, persistencia y activación; no hay cobros habilitados.

## Evidencia disponible

La captura proporcionada por el propietario muestra un Lightning Address de QvaPay con estas opciones visibles:

- Dirección Lightning mostrada: `axyronatomic@qvpay.me`.
- Modo seleccionado: recibir en dólares (USD), con conversión al precio del momento.
- Comisión de conversión mostrada en esa pantalla: 0,5 %.
- Alternativa: recibir satoshis sin conversión.
- Límites visibles en la cuenta al momento de la captura: pago de USD 0,10 a USD 500 y disponibilidad diaria de USD 1.000 de USD 1.000.

Los límites, la comisión y la disponibilidad son datos de la pantalla de esa cuenta y pueden cambiar. No deben codificarse como límites contractuales o tarifas universales de QvaPay. La comisión de conversión mostrada tampoco debe confundirse con una comisión de AXION ATOMIC.

## Diseño de integración para el primer lanzamiento

1. AXION ATOMIC crea y persiste una orden interna antes de mostrar instrucciones de pago.
2. La orden conserva usuario, producto, importe esperado, moneda, estado, vencimiento e identificador interno único.
3. La interfaz muestra el método Lightning que QvaPay autorice para AXION ATOMIC y las instrucciones vigentes.
4. El backend solo marca la orden como pagada después de verificar el pago mediante un mecanismo servidor-a-servidor oficialmente soportado por QvaPay.
5. La confirmación debe vincularse inequívocamente con la orden y comprobar importe, moneda, estado, identificador/transacción y destinatario.
6. La acreditación de suscripción o créditos se realiza una sola vez, dentro de una transacción idempotente.
7. Eventos duplicados, tardíos, manipulados, incompletos o con importe incorrecto se registran para conciliación y no acreditan saldo.
8. Reembolsos y reversiones se registran con movimientos compensatorios; nunca se borra el historial económico.

## Contrato oficial y límites verificados

La documentación oficial de QvaPay confirma:

- `GET /user/lightning-address` con Bearer del titular devuelve estado, límites, comisión y los últimos cobros con `sats`, `credit_usd`, `comment`, `paid_at`, `transaction_uuid` y `address`.
- El endpoint LNURL público `/.well-known/lnurlp/{name}` y su `callback` permiten generar una invoice BOLT11 por importe exacto y con comentario LUD-12.
- `GET /coins` publica el precio BTC/USD utilizado para convertir el importe.
- No existe webhook firmado específico de Lightning Address: la conciliación se hace por consulta autenticada y paginada.
- El comentario lo escribe el pagador y no está verificado; la correlación exige referencia, sats exactos, dirección y `transaction_uuid`.
- `credit_usd` es el neto tras comisión, no el bruto de la invoice.
- Límites y comisiones son dinámicos y deben leerse en ejecución.

Pendiente antes de activar: custodia del token del titular, catálogo/precios aprobados, persistencia de invoices, sincronización paginada, rutas de checkout, conciliación de duplicados/tardíos y pruebas en sandbox oficial. No inventar endpoints, cabeceras, firmas HMAC, payloads ni eventos. No aceptar capturas de pantalla del usuario como prueba de pago.

## Estado de activación

- Aprobación comercial: confirmada por el propietario.
- Método de recepción previsto: Lightning Address de QvaPay.
- Contrato técnico oficial: confirmado.
- Adaptador de cliente (`api/qvapay_lightning.py`): implementado y probado con transporte simulado.
- Persistencia de invoices y sincronización de cobros: pendientes.
- Webhook Lightning: no existe; se usa consulta autenticada del titular.
- Acreditación automática: deshabilitada.
- Cobros reales: deshabilitados.

La integración solo puede habilitarse después de probar el flujo completo en el entorno de pruebas oficial de QvaPay, incluida la idempotencia y conciliación de eventos duplicados o inválidos.
