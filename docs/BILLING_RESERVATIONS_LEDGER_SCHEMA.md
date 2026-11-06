# Base PostgreSQL de cuotas y créditos — migración 007

La migración `007_billing_reservations_ledger.sql` añade el esquema persistente de cuotas, lotes de crédito, reservas, asignaciones y movimientos del libro económico.

## Garantías previstas

- Titularidad individual por usuario; el proyecto solo atribuye consumo.
- Periodos de cuota con límites UTC, zona IANA y cantidades reservadas/consumidas.
- Lotes de crédito con disponible, reservado y consumido, preparados para orden FEFO.
- Reservas con clave de idempotencia única por usuario y hash SHA-256 del payload.
- Estados `unknown` y `review` para resultados inciertos; no liberar saldo solo por expiración.
- Asignaciones diferenciadas para cuota diaria, suscripción y créditos comprados.
- El ledger registra movimientos con claves idempotentes; la migración 008 rechaza UPDATE, DELETE y TRUNCATE mediante triggers.
- Relaciones económicas protegidas frente a borrado en cascada.

## Alcance y limitaciones

Las operaciones transaccionales iniciales están en `api/billing_reservations.py`: `reserve_credits` serializa claves idempotentes, bloquea cuotas y lotes con `FOR UPDATE`, aplica cuota diaria → suscripción y solo usa lotes comprados FEFO cuando `purchased_fallback_allowed=True` para el plan, registrando reservas en una transacción. `settle_reservation` liquida hasta el importe reservado y devuelve el exceso; un uso superior pasa a `review`. `mark_reservation_unknown` conserva saldo reservado ante resultados inciertos. La migración 008 bloquea UPDATE, DELETE y TRUNCATE del ledger. Estas operaciones aún no están conectadas a rutas HTTP ni a inferencia. No debe considerarse listo para facturar hasta superar pruebas PostgreSQL de concurrencia, idempotencia, atomicidad y recuperación.

## Medición de inferencia y tarifa

El módulo `api/billing_metering.py` incorpora `ModelRatePolicy` y `calculate_inference_charge` como cálculo puro de uso. Solo acepta una política habilitada mediante booleano literal `True`, versión y nombre no vacíos, modelo solicitado y modelo devuelto por Ollama coincidentes, inferencia final (`done=True`) y contadores de entrada/salida procedentes de `ollama_response`. Los contadores desconocidos, una respuesta no final o una identidad de modelo distinta bloquean la liquidación. La salida `InferenceCharge` conserva la versión y ponderadores aplicados.

Las pruebas están en `tests/test_billing_metering.py`. Este helper todavía no reserva saldo, no invoca inferencia, no escribe en el ledger y no está conectado a `/workspace/chat/completions`. La telemetría Shadow Mode sigue sin ser una fuente de cobro. El modelo ATOMIC CODE no debe facturarse hasta implementar una reserva máxima segura antes de ejecutar, liquidación posterior y recuperación auditada ante resultados inciertos.

## Contrato obligatorio de implementación

1. Validar identidad y clave idempotente; misma clave con hash distinto debe producir conflicto.
2. En una sola transacción, bloquear periodos de cuota y lotes FEFO con `SELECT ... FOR UPDATE`, siempre en orden estable.
3. Comprobar capacidad y crear reserva/asignaciones y movimientos de reserva antes de confirmar.
4. Ejecutar inferencia fuera de la transacción.
5. Conciliar el uso medido en otra transacción idempotente; liberar exceso reservado y consumir solo el importe real.
6. Ante resultado incierto, conservar la reserva en `unknown` o `review`; nunca asumir consumo cero ni liberar automáticamente.
7. Probar en PostgreSQL real, incluyendo dos workers intentando reservar el mismo saldo. Las pruebas de integración en `tests/test_billing_reservations_postgres.py` cubren idempotencia, conflicto de payload, liquidación parcial repetida, concurrencia, FEFO, permiso explícito para créditos comprados y retención de reservas desconocidas. El job PostgreSQL de CI ejecuta ambos archivos junto con las comprobaciones de esquema de `tests/test_postgres_migrations.py`.

La autenticación, autorización de proyecto y política comercial deben validarse en la capa superior antes de invocar el servicio. No ejecutar estas migraciones en el VPS como parte del trabajo de repositorio.
