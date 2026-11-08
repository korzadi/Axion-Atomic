# QvaPay — método de cobro previsto para AXION ATOMIC

**Estado:** aprobación comercial de QvaPay confirmada por el propietario; integración técnica todavía bloqueada y sin cobros habilitados.

## Evidencia disponible

La captura proporcionada por el propietario muestra un Lightning Address de QvaPay con estas opciones visibles:

- Dirección Lightning mostrada: `axionatomic@qvpay.me`.
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

## Verificaciones obligatorias con QvaPay

La captura confirma la interfaz de recepción Lightning, pero no demuestra que exista una API de facturas, metadata para asociar un pago a una orden, webhook firmado ni endpoint de consulta de transacciones. Antes de implementar el adaptador deben confirmarse oficialmente:

- Si QvaPay permite generar una invoice Lightning distinta por orden o asociar una referencia externa.
- Si existe webhook o notificación firmada para pagos recibidos y cuál es el esquema exacto de firma.
- Si el backend puede consultar el estado de una transacción y obtener su identificador, importe, moneda, destinatario y fecha.
- Qué identificador estable permite correlacionar el pago con una orden de AXION ATOMIC.
- Cómo se notifican pagos parciales, duplicados, expirados, reembolsados o revertidos.
- Si USD se confirma como importe de liquidación o solo como modo de conversión de la cuenta.
- Límites y comisiones aplicables a la cuenta comercial de AXION ATOMIC en el momento de operar.

No inventar endpoints, cabeceras, firmas HMAC, payloads ni eventos. No aceptar capturas de pantalla del usuario como prueba de pago.

## Estado de activación

- Aprobación comercial: confirmada por el propietario.
- Método de recepción previsto: Lightning Address de QvaPay.
- Integración backend: pendiente de documentación/contrato técnico oficial.
- Webhook/consulta y verificación: no implementados ni probados.
- Acreditación automática: deshabilitada.
- Cobros reales: deshabilitados.

La integración solo puede habilitarse después de probar el flujo completo en el entorno de pruebas oficial de QvaPay, incluida la idempotencia y conciliación de eventos duplicados o inválidos.
