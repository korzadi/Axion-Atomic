# Integración QvaPay — estado y contrato técnico

## Estado comercial y técnico

- Aprobación comercial comunicada por el propietario: `APPROVED`.
- Método elegido por el propietario para recibir pagos: Lightning Address de QvaPay (`axionatomic@qvpay.me`), con recepción en USD/conversión automática según la pantalla compartida.
- Integración técnica: bloqueada hasta confirmar el contrato servidor-a-servidor específico de Lightning Address.
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

Son datos de una pantalla/cuenta en ese momento, no tarifas ni límites contractuales permanentes. La comisión de conversión tampoco debe confundirse con una comisión de AXION ATOMIC.

## Confirmaciones necesarias de QvaPay para Lightning Address

Antes de implementar o activar el adaptador, obtener confirmación oficial por escrito de:

1. Si cada orden puede generar una invoice Lightning única o incluir una referencia externa.
2. Si existe webhook/notificación de pagos Lightning entrantes y su autenticación/firma exacta.
3. Si existe endpoint servidor-a-servidor para consultar una transacción Lightning y obtener identificador estable, importe, moneda, destinatario y estado final.
4. Cómo correlacionar inequívocamente cada pago con una orden de AXION ATOMIC.
5. Cómo se representan pagos parciales, pagos repetidos, tardíos, expirados, reembolsados o revertidos.
6. Si USD es el importe de liquidación verificable o solo una preferencia de conversión de la cuenta.
7. Límites y comisiones vigentes para la cuenta comercial al momento de operar.

No inventar endpoints, cabeceras, payloads, firmas, eventos ni campos. No aceptar capturas de pantalla como prueba de pago.

## Diseño interno permitido mientras se confirma el contrato

Se puede desarrollar el Payment Manager independiente del proveedor: órdenes internas persistidas, estados, vencimientos, historial append-only, idempotencia, conciliación manual/revisión y acreditación transaccional preparada. El adaptador de QvaPay debe permanecer desconectado hasta que el contrato específico de Lightning esté confirmado y probado.

La futura acreditación debe validar desde backend la identidad de la transacción, orden, destinatario, importe, moneda y estado final; registrar evento y movimiento económico en una transacción atómica; y procesar duplicados sin volver a acreditar. Los reembolsos/reversiones deben ser movimientos compensatorios, nunca borrado del historial.

## Estado de activación

- Aprobación comercial: confirmada por el propietario.
- Método elegido: Lightning Address QvaPay.
- Merchant API: documentada públicamente, pero es un flujo distinto y no se considera integración del método elegido.
- Contrato técnico de Lightning Address: pendiente de confirmación oficial.
- Payment Manager: pendiente de implementación.
- Webhook/consulta Lightning: no implementados ni probados.
- Acreditación automática: deshabilitada.
- Cobros reales: deshabilitados.

## Fuentes oficiales consultadas

- Introducción: https://www.qvapay.com/docs
- Crear factura Merchant: https://www.qvapay.com/docs/merchants/create-invoice
- Detalle de transacción Merchant: https://www.qvapay.com/docs/merchants/transaction-detail
- Firma de pagos mini-app: https://www.qvapay.com/docs/miniapps/payments
