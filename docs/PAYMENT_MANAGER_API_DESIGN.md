# Diseño de API del administrador de pagos

Estado: diseño técnico; todavía no hay rutas HTTP de pagos ni panel administrativo publicados.

## Alcance inmediato

La migración `016_payment_orders_manager.sql` y `api/payment_manager.py` implementan el núcleo de persistencia de órdenes. Este diseño define cómo exponerlo sin habilitar cobros ni permitir que el navegador confirme transacciones.

## Rutas previstas

### Usuario autenticado

- `GET /billing/catalog`: devuelve únicamente los productos publicados por el servidor, con precio en centavos USD, créditos y disponibilidad.
- `POST /billing/orders`: crea una orden usando exclusivamente un `product_code` del catálogo del servidor. No acepta del cliente el importe, moneda, créditos, destinatario ni estado.
- `GET /billing/orders`: lista únicamente las órdenes del usuario autenticado, con paginación acotada.
- `GET /billing/orders/{order_id}`: consulta una orden solo si pertenece al usuario autenticado.

Las rutas mutables deben exigir sesión activa, protección CSRF, rate limit distribuido y validación de que el usuario está activo. Los errores de orden inexistente y orden ajena deben ser indistinguibles.

### Operaciones administrativas

No se habilitará un panel administrativo ni rutas de conciliación hasta disponer de un rol administrativo persistente, autorización centralizada y auditoría de cada decisión. No se debe inferir el rol a partir de correo, nombre, ID enviado por el navegador ni una variable de frontend.

### Verificación del proveedor

No se publica ninguna ruta para confirmar pagos desde el navegador. El futuro adaptador solo podrá llamar a `confirm_verified_payment` después de demostrar una verificación servidor-a-servidor auténtica y específica para Lightning Address.

La documentación de Merchant Invoice de QvaPay no demuestra por sí sola que Lightning Address proporcione factura por orden, consulta de estado o webhook firmado. No se reutilizarán esos mecanismos como si fueran equivalentes.

## Reglas obligatorias

1. El catálogo y sus precios son propiedad del servidor; nunca confiar en el precio enviado por el cliente.
2. Una observación de pago no equivale a un pago verificado y no concede créditos.
3. Una transacción del proveedor solo puede asociarse a una orden.
4. La confirmación, la transacción, el lote de créditos, el asiento del ledger y el cambio a `paid` deben ocurrir en una única transacción PostgreSQL.
5. Reintentos idempotentes deben devolver el resultado ya registrado, sin duplicar créditos.
6. Importe, moneda, destinatario, referencia de orden y ventana temporal deben coincidir exactamente.
7. Pagos tardíos, parciales, excesivos, duplicados o con datos ambiguos pasan a revisión y no conceden créditos automáticamente.
8. Los eventos de auditoría son append-only; no se guardan secretos ni datos de pago innecesarios.
9. No se aceptan capturas de pantalla ni declaraciones del frontend como evidencia.
10. La integración real permanece deshabilitada hasta que QvaPay confirme por escrito el contrato técnico aplicable a Lightning Address.

## Condiciones para habilitar

- Confirmación de QvaPay sobre identificador único por orden, verificación del estado desde servidor, firma/autenticación, expiración, reintentos y política de pagos tardíos.
- Catálogo comercial aprobado y versionado.
- Rol administrativo y permisos probados.
- Pruebas de aislamiento entre usuarios, CSRF, rate limits, concurrencia, idempotencia, pagos duplicados y conciliación.
- Revisión de seguridad y autorización explícita antes de cualquier despliegue o cobro real.

## Estado operativo

- No se han activado cobros.
- No se ha conectado un webhook ni un cliente de QvaPay.
- No se han expuesto rutas HTTP de pagos.
- No se ha desplegado ni modificado el VPS.
