# Integración QvaPay — estado y contrato técnico

## Estado comercial y técnico

- Aprobación comercial comunicada por el propietario: `APPROVED`.
- Integración técnica: en desarrollo; no declarar `PRODUCTION_READY` hasta completar pruebas verificables con el simulador oficial y revisión del flujo de acreditación.
- Credenciales: no están disponibles en el repositorio y no deben solicitarse ni publicarse en commits, incidencias o logs.
- No se han realizado cobros reales.

## Contrato oficial consultado

- Base API: `https://api.qvapay.com`.
- Crear factura: `POST /v2/create_invoice`.
- Autenticación servidor-servidor: headers `app-id` y `app-secret`.
- Campos documentados: `amount`, `description`, `remote_id`, `webhook`, `products`, `expire_at`.
- Verificación servidor: `POST /v2/transactions/:uuid` con las credenciales de la App.
- Webhook: cuerpo crudo JSON, header `x-qvapay-signature` con `sha256=<hex>` HMAC-SHA256 usando el `app-secret`, y `x-qvapay-timestamp`.
- La transacción debe conciliarse en backend; una redirección del navegador no acredita un pago.
- `transaction_uuid` es la clave de idempotencia recomendada para procesar notificaciones repetidas.

## Reglas de implementación

1. Crear una factura por orden interna y persistir la relación entre `remote_id` y `transaction_uuid`.
2. Validar firma del webhook sobre los bytes originales antes de parsear el JSON.
3. Validar la antigüedad del timestamp y mantener registro idempotente por `transaction_uuid`.
4. Consultar la transacción en QvaPay desde el backend y comprobar UUID, `remote_id`, importe y estado `paid` contra la orden local.
5. Aplicar el crédito o plan en la misma transacción de base de datos que registra el pago y su evento procesado.
6. No acreditar a partir de datos del frontend ni únicamente de un webhook no conciliado.
7. No emitir reembolsos hasta confirmar el endpoint y su semántica en la documentación vigente.
8. No ejecutar pruebas con dinero real; utilizar el simulador o modo de prueba oficial.

## Pendiente para producción

- Implementar Payment Manager y el adaptador QvaPay.
- Definir y migrar tablas de órdenes, eventos y ledger después de inspeccionar el esquema comercial existente.
- Implementar endpoint webhook con cuerpo crudo y verificación HMAC.
- Implementar conciliación backend y acreditación idempotente.
- Añadir pruebas unitarias y pruebas oficiales en modo de prueba.
- Configurar App ID, App Secret y URL pública de webhook directamente en el gestor de secretos del despliegue; nunca en Git.

## Fuente oficial

- Introducción: https://www.qvapay.com/docs
- Crear factura: https://www.qvapay.com/docs/merchants/create-invoice
- Detalle de transacción: https://www.qvapay.com/docs/merchants/transaction-detail
- Flujo y firma de webhook: https://www.qvapay.com/docs/miniapps/payments
