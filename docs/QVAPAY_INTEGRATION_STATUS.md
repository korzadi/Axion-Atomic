# Integración QvaPay — estado y contrato técnico

## Estado comercial y técnico

- Aprobación comercial comunicada por el propietario: `APPROVED`.
- Método elegido por el propietario para recibir pagos: Lightning Address de QvaPay (`axionatomic@qvpay.me`), con recepción en USD/conversión automática según la pantalla compartida.
- Integración técnica: contrato oficial de Lightning Address confirmado en la documentación pública el 8 de noviembre de 2026.
- Adaptador de solo lectura/creación de invoice implementado en `api/qvapay_lightning.py`; la persistencia de invoices, la sincronización y las rutas HTTP siguen pendientes.
- No se han realizado cobros reales y la acreditación automática permanece deshabilitada.
- Credenciales, códigos de acceso y secretos no deben solicitarse ni publicarse en Git, incidencias o logs.

## Distinción obligatoria entre dos productos/flows

La documentación pública consultada de QvaPay describe un flujo Merchant API de facturas:

- Base API documentada: `https://api.qvapay.com`.
- Crear factura Merchant: `POST /v2/create_invoice`, con credenciales de aplicación y campos como `amount`, `description`, `remote_id`, `webhook` y `expire_at`.
- Consultar transacción Merchant: `POST /v2/transactions/:uuid`.
- Para el flujo de mini-apps se documenta una firma HMAC-SHA256 sobre el cuerpo crudo mediante `x-qvapay-signature`, además de timestamp.

**Ese contrato Merchant/mini-app no demuestra que el Lightning Address de la cuenta tenga las mismas funciones.** No se debe sustituir el método Lightning elegido por facturas Merchant, ni asumir que acepta `remote_id`, webhook, HMAC, invoice por orden o consulta API.

## Evidencia del método Lightning

La captura compartida por el propietario mostraba:

- Dirección Lightning: `axionatomic@qvpay.me`.
- Recepción en USD con conversión automática.
- Comisión de conversión mostrada en esa pantalla: 0,5 %.
- Límites visibles en ese momento: USD 0,10–500 por pago y disponibilidad diaria de USD 1.000.

Son datos de una pantalla/cuenta en ese momento, no tarifas ni límites contractuales permanentes. La comisión de conversión tampoco debe confundirse con una comisión de AXYRON ATOMIC.

## Contrato oficial confirmado

La documentación pública de QvaPay describe el siguiente flujo específico de Lightning Address:

1. `GET https://api.qvapay.com/user/lightning-address` con `Authorization: Bearer {token}` del titular devuelve el estado de la dirección, límites, comisiones y los últimos cobros (20 por página). Cada cobro incluye `sats`, `credit_usd`, `comment`, `paid_at`, `transaction_uuid` y `address`.
2. `GET https://qvpay.me/.well-known/lnurlp/{name}` devuelve un `payRequest` LUD-06 con `callback`, `minSendable`, `maxSendable` y `commentAllowed`.
3. `GET {callback}?amount={msat}&comment={texto}` devuelve una invoice BOLT11 (`pr`) por el importe exacto. El comentario usa LUD-12 (máximo 255 caracteres).
4. `GET https://api.qvapay.com/coins` es público y publica el precio BTC/USD vigente.

### Limitaciones verificadas

- No existe webhook firmado específico para Lightning Address; la conciliación debe hacerse consultando la API con el token del titular.
- El `comment` lo escribe quien paga y no está verificado. Solo sirve como referencia de correlación junto con importe exacto en sats, dirección destino y `transaction_uuid`; no como prueba aislada.
- `credit_usd` es el neto acreditado tras la comisión, no el importe bruto de la invoice.
- La API devuelve los últimos 20 cobros por página; una conciliación completa requiere paginación y una ventana de seguridad.
- Los límites y comisiones son dinámicos y deben leerse en tiempo de ejecución; no se codifican como constantes.
- No se debe usar el flujo Merchant `/v2/create_invoice` como sustituto del Lightning Address elegido.

No inventar endpoints, cabeceras, payloads, firmas, eventos ni campos. No aceptar capturas de pantalla como prueba de pago.

## Estado del Payment Manager y del adaptador

El Payment Manager interno (`api/payment_manager.py`) ya implementa órdenes persistidas, estados, vencimientos, historial append-only, verificación server-side, idempotencia y acreditación transaccional. El adaptador `api/qvapay_lightning.py` implementa el contrato oficial de consulta y creación de invoices con transporte inyectable y pruebas unitarias.

Pendiente antes de activar cobros:

1. Custodia del token del titular y configuración `QVAPAY_USER_TOKEN` fuera del repositorio.
2. Catálogo y precios aprobados que permitan crear órdenes sin confiar en importes enviados por el navegador.
3. Persistencia de invoices (sats, precio BTC, comisión y estado) y sincronización paginada de cobros.
4. Rutas HTTP de checkout y conciliación con CSRF, permisos e idempotencia.
5. Pruebas en el entorno de pruebas oficial de QvaPay, incluyendo pagos duplicados, tardíos y manipulados.
6. Revisión operativa de reembolsos, pagos no conciliados y límites diarios.

La futura acreditación debe validar desde backend la identidad de la transacción, orden, destinatario, importe, moneda y estado final; registrar evento y movimiento económico en una transacción atómica; y procesar duplicados sin volver a acreditar. Los reembolsos/reversiones deben ser movimientos compensatorios, nunca borrado del historial.

## Estado de activación

- Aprobación comercial: confirmada por el propietario.
- Método elegido: Lightning Address QvaPay.
- Merchant API: documentada públicamente, pero es un flujo distinto y no se considera integración del método elegido.
- Contrato técnico de Lightning Address: confirmado oficialmente.
- Adaptador de cliente Lightning: implementado y probado con transporte simulado.
- Payment Manager: implementado.
- Persistencia de invoices y sincronización de cobros: pendientes.
- Webhook Lightning: no existe; se usa consulta autenticada del titular.
- Rutas de checkout: no implementadas.
- Acreditación automática: deshabilitada.
- Cobros reales: deshabilitados.

## Fuentes oficiales consultadas

- Introducción: https://www.qvapay.com/docs
- Lightning Address (API del titular y LNURL): https://www.qvapay.com/docs/user/lightning-address
- Listar coins y precio BTC/USD: https://www.qvapay.com/docs/coins/list
- Crear factura Merchant: https://www.qvapay.com/docs/merchants/create-invoice
- Detalle de transacción Merchant: https://www.qvapay.com/docs/merchants/transaction-detail
- Firma de pagos mini-app: https://www.qvapay.com/docs/miniapps/payments
