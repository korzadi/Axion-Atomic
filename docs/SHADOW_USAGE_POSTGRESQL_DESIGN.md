# AXION ATOMIC — Diseño de persistencia de telemetría Shadow Mode en PostgreSQL

**Estado:** implementado parcialmente en `main` mediante migración 006 y escritura best-effort; no es facturación.  
**Fecha:** 6 de noviembre de 2026.  
**Objetivo:** pasar de eventos JSON en logs a registros consultables y auditables de uso de inferencia, sin activar cuotas, créditos, reservas, facturación ni cobros.

## 1. Alcance y límites

Esta fase almacena únicamente el resultado de observación de una inferencia completada por el proveedor. No calcula precios, no descuenta créditos y no bloquea peticiones.

Incluye:
- Identidad individual autenticada (user_id) y atribución opcional al proyecto (project_id).
- Identificador único de solicitud para evitar duplicar un evento si la persistencia se reintenta.
- Modelo solicitado y modelo devuelto por el proveedor.
- Contadores reales de input/output reportados por Ollama.
- Duraciones del motor en nanosegundos.
- Estado de disponibilidad de los contadores y marca temporal UTC.

Excluye:
- Prompts, historial, system prompts, documentos RAG, respuestas, embeddings y contenido de herramientas.
- Cookies, tokens de sesión, API keys, cabeceras de autorización, secretos y credenciales.
- Tarifas, costes, saldos, lotes de créditos, cuotas, reservas, pagos, reembolsos y decisiones de facturación.
- La ruta heredada /v1 mientras use una clave compartida sin identidad individual verificable.
- Streaming y resultados parciales hasta que exista un contrato de eventos separado.

## 2. Tabla propuesta: inference_usage_events

La tabla se añadió mediante `migrations/006_inference_usage_events.sql`, sin editar migraciones históricas.

| Campo | Tipo PostgreSQL | Regla |
|---|---|---|
| event_id | UUID | PK, generado por la aplicación |
| request_id | UUID | NOT NULL, UNIQUE; estable durante los reintentos de persistencia |
| user_id | TEXT | FK a users(id), NOT NULL, ON DELETE RESTRICT |
| project_id | TEXT | FK a projects(id), nullable, ON DELETE RESTRICT |
| provider | TEXT | No se almacena en la primera versión; el adaptador configurado es Ollama |
| requested_model | TEXT | NOT NULL |
| returned_model | TEXT | nullable |
| prompt_tokens | BIGINT | nullable; CHECK >= 0 |
| output_tokens | BIGINT | nullable; CHECK >= 0 |
| usage_source | TEXT | NOT NULL; ollama_response o unavailable |
| done | BOOLEAN | nullable |
| total_duration_ns | BIGINT | nullable; CHECK >= 0 |
| load_duration_ns | BIGINT | nullable; CHECK >= 0 |
| prompt_eval_duration_ns | BIGINT | nullable; CHECK >= 0 |
| eval_duration_ns | BIGINT | nullable; CHECK >= 0 |
| observed_at | TIMESTAMPTZ | NOT NULL, generado en servidor |


Reglas de integridad:
- No convertir contadores o duraciones desconocidos en cero.
- usage_source='ollama_response' solo cuando input y output sean enteros no negativos conocidos.
- Si falta cualquiera de los dos contadores, usage_source='unavailable'; se conserva cualquier contador individual que sí esté disponible.
- Los valores booleanos no son contadores válidos aunque Python considere bool una subclase de int.
- request_id identifica una inferencia, no un intento de cobro. La restricción UNIQUE evita insertar dos observaciones para la misma solicitud.
- Las referencias históricas no deben borrarse en cascada al eliminar usuarios o proyectos. La política de baja/anónimo debe definirse aparte, respetando retención y obligaciones legales.

## 3. Índices iniciales

Crear únicamente índices justificados por consultas previstas:
- (user_id, observed_at DESC) para historial individual.
- (project_id, observed_at DESC) para análisis por proyecto.
- (requested_model, observed_at DESC) para análisis por modelo.

No crear índices por cada columna ni particionar prematuramente. Revisar volumen real, cardinalidad y planes de consulta antes de añadir más.

## 4. Inmutabilidad y permisos

- El rol de ejecución de AXION obtiene INSERT y SELECT estrictamente necesarios; no UPDATE ni DELETE sobre la tabla.
- Un rol separado de migración/propietario controla DDL y mantenimiento.
- Los reportes de usuario consultan únicamente filas cuyo user_id coincide con la identidad autenticada; el filtro de project_id no sustituye autorización de membresía.
- Los reportes administrativos requieren RBAC global independiente de los roles de proyecto.
- Ningún endpoint debe aceptar user_id como autoridad enviada por el cliente.
- Las correcciones no modifican eventos existentes: se modelan como eventos compensatorios o nuevas versiones relacionadas, si una fase futura lo requiere.
- La retención y borrado legal deben ser una política explícita, auditada y separada del rol normal de la aplicación. No fijar un plazo arbitrario antes de revisar requisitos legales/comerciales.

## 5. Flujo de escritura propuesto

1. La ruta autenticada genera un request_id UUID antes de iniciar la inferencia.
2. El adaptador devuelve InferenceResult con contadores reales o None.
3. Si la inferencia finaliza, la ruta intenta insertar un evento usando el mismo request_id mediante `api/usage_events.py`.
4. La inserción se hace en una transacción breve e independiente; no mantener una transacción PostgreSQL abierta mientras Ollama genera.
5. `ON CONFLICT (request_id) DO NOTHING` hace idempotente la repetición de la misma observación.
6. Si PostgreSQL falla, la respuesta de inferencia sigue siendo exitosa. Se registra una métrica/log operacional sin incluir contenido sensible y se marca la persistencia como no confirmada.
7. En esta fase no existe cola de reintentos duradera. Antes de prometer entrega garantizada se deberá diseñar outbox/cola durable, límites de reintentos y reconciliación.

**Importante:** una escritura que falla después de una inferencia exitosa puede perder la observación. Shadow Mode acepta explícitamente esa limitación; no se debe presentar como telemetría completa ni como base contable.

## 6. Consultas y privacidad

Las consultas iniciales deben ser agregadas o paginadas y limitarse por identidad/proyecto:
- Consumo por usuario y periodo.
- Consumo por proyecto y periodo.
- Consumo por modelo y periodo.
- Porcentaje de eventos con contadores no disponibles.
- Duración reportada por el proveedor.

No exponer datos de otros usuarios a través de filtros manipulables. No almacenar contenido de prompts para “depurar tokens”; los contadores de Ollama son la fuente primaria.

## 7. Pruebas obligatorias antes de una migración

### Esquema PostgreSQL
- Migración nueva y aditiva; checksum estable; no editar archivos ya aplicados.
- Restricciones CHECK para contadores/duraciones.
- UNIQUE de request_id.
- FK y política de eliminación no destructiva.
- Índices y consultas bajo PostgreSQL real de prueba, no SQLite como sustituto de toda la semántica PostgreSQL.

### Persistencia
- Inserción válida con ambos contadores.
- Inserción con contador ausente y usage_source='unavailable'.
- Rechazo de negativos y valores incompatibles.
- Reintento con el mismo request_id sin duplicación.
- Dos solicitudes distintas concurrentes.
- Fallo de DB no cambia el resultado HTTP de una inferencia exitosa.
- La aplicación no puede UPDATE/DELETE.
- Un usuario no puede consultar eventos de otro usuario ni de proyectos ajenos.
- No aparecen prompts, respuestas, cookies, credenciales ni secretos en filas/logs.

### CI
La suite SQLite actual es útil para lógica general, pero no acredita constraints, índices, roles, transacciones ni concurrencia de PostgreSQL. Se añadió un job `postgres-migrations` al CI con PostgreSQL 16 efímero: aplica las migraciones dos veces para comprobar idempotencia y ejecuta `tests/test_postgres_migrations.py` sobre el esquema real. El resultado de ese job aún debe verificarse en GitHub Actions; esta ampliación no prueba todavía la futura tabla de telemetría.

## 8. Orden seguro de implementación

1. Revisar el resultado de CI actual y cerrar las incompatibilidades de Shadow Mode.
2. Ejecutar y cerrar el nuevo job PostgreSQL de CI; ampliar sus pruebas cuando se implemente el repositorio de telemetría.
3. Implementar migración 006 solo después de aprobar este diseño y sus pruebas.
4. Añadir un repositorio de escritura append-only y pruebas de aislamiento ante fallo de DB.
5. Añadir consultas de lectura protegidas por identidad/RBAC.
6. Observar cobertura, pérdidas y volumen en Shadow Mode.
7. Solo después diseñar el motor de reservas/cuotas/ledger en documentos separados.

## 9. Criterios de salida

Esta fase solo se considera completa cuando:
- La migración aditiva se aplica en una base PostgreSQL de prueba limpia y en una base con esquema previo compatible.
- La suite PostgreSQL de CI pasa.
- La idempotencia y el aislamiento entre usuarios están probados.
- Los eventos no contienen contenido sensible.
- La caída de PostgreSQL no convierte una respuesta exitosa de Ollama en error.
- Se documentan retención, acceso, métricas de pérdida y límites de observabilidad.

**Estado actual:** migración 006 y persistencia best-effort publicadas. No se han ejecutado en el VPS ni se ha activado facturación, cuotas, reservas, créditos o pagos. La aplicación todavía no tiene permisos de tabla restringidos ni reintentos durables.
