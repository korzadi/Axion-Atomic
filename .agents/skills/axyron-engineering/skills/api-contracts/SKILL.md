---
name: api-contracts
description: Diseña y mantiene APIs HTTP, contratos JSON, autenticación, autorización, errores y compatibilidad entre frontend y backend.
---
# Diseño de APIs y contratos

- Inspecciona routers, esquemas, clientes, documentación y pruebas existentes antes de definir rutas.
- Usa nombres, métodos, códigos HTTP, formatos y versionado coherentes con el proyecto.
- Define request/response, campos obligatorios/opcionales, límites, paginación y errores.
- Diferencia autenticación de autorización; comprueba propietario, rol y ámbito del recurso en cada operación.
- Evita IDOR, mass assignment, over-fetching y filtración de datos.
- Valida entradas con límites de tamaño y tipos; normaliza solo cuando sea seguro.
- Para operaciones mutables considera idempotencia, concurrencia, transacciones y auditoría.
- No devuelvas secretos ni detalles internos en errores.
- Actualiza cliente frontend, esquemas, OpenAPI/documentación y tests en el mismo cambio.
- Nunca declares una ruta disponible por aparecer en un mock, README o interfaz: verifica implementación ejecutable.
