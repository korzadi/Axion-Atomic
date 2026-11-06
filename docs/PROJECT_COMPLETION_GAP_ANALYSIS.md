# Estado real del proyecto AXION ATOMIC

**Rama revisada:** `hardening/phase-a-b`  
**Estado:** desarrollo/hardening; NO apto para producción.  
**Alcance de esta revisión:** inspección estática del repositorio y cambios documentales/de código mediante GitHub. No se ejecutaron pruebas, contenedores, migraciones ni despliegues.

## Identidad y restricciones confirmadas

- Producto: AXION ATOMIC.
- Agente: AXION.
- Modelo objetivo: ATOMIC CODE 1.1.
- Interfaz propia prevista: AXION STUDIO.
- Ollama existente se trata como servicio externo; no instalar, actualizar ni alterar sus datos.
- No se integra ni depende de Open WebUI.
- No se accede al VPS, no se despliega, no se ejecutan migraciones ni se modifican secretos.
- La rama de trabajo no se fusiona automáticamente con `main`.

## Implementado en esta rama (estático; pruebas pendientes)

- Filtro de recuperación Qdrant por `project_id` y validación de ese identificador.
- API key con fallo cerrado cuando no existe o es débil, y comparación de tiempo constante.
- GitManager con preview de archivos untracked, selección explícita de rutas y detección de patrones de secretos.
- Persistencia de ejecuciones/acciones y protección contra reutilizar el mismo hash con una carga útil distinta.
- Actualización condicional de aprobaciones y expiración.
- Health endpoint que consulta PostgreSQL, Ollama y Qdrant.
- Dockerfile copia los módulos internos requeridos.
- Contrato y estado de integración comercial/técnica QvaPay documentados.
- Dockerfile ya no ejecuta migraciones al arrancar: se deben lanzar explícitamente por un operador tras revisar el backup, el diff y el entorno destino.

## Bloqueadores críticos antes de producción

### 1. Identidad, sesiones y autorización multiusuario
No existe todavía autenticación real de usuarios ni RBAC conectado a las rutas. Una API key global no constituye identidad de usuario. El cliente puede enviar un `project_id`; la API aún no demuestra pertenencia/autorización del usuario a ese proyecto. Hasta implementar y probar usuarios, sesiones, membresías y roles, no exponer endpoints de chat, ingestión ni agente a clientes no confiables.

### 2. Agente y API
La API actual usa el planner y el almacén de aprobaciones legado. El nuevo `CodingAgent`, `RunStore` y runtime persistente no están conectados a las rutas HTTP. Las aprobaciones antiguas registran intención y no ejecutan herramientas. Falta diseñar endpoints de runs, acciones, aprobación/rechazo, expiración, restauración y reconciliación, todos limitados por usuario/proyecto. No afirmar ejecución real desde la API.

### 3. AXION STUDIO
No se ha encontrado una aplicación frontend propia completa en las rutas inspeccionadas. Falta crear interfaz con registro/login, proyectos, chat, carga de conocimiento, estado de agente, vista previa de cambios, aprobación explícita, logs, consumo, facturación y controles de privacidad/accesibilidad.

### 4. Aislamiento y sandbox
El aislamiento RAG por proyecto no reemplaza autorización. Falta enlazar workspace, Git y sandbox con el proyecto autenticado, aplicar límites de CPU/RAM/tiempo/tamaño, políticas de red, cuotas y protección contra traversal/symlinks/escape. Revisar el backend real del sandbox y probarlo en entorno aislado antes de habilitar herramientas mutables.

### 5. Modelo
La configuración de Ollama apunta a un nombre de modelo, pero no se ha verificado desde esta rama que el servicio cargue ATOMIC CODE 1.1 ni que el tokenizer/contexto/plantilla sean compatibles. Falta prueba de inferencia, evaluación reproducible, límites de contexto, cancelación, streaming y selección de modelos. No afirmar que el modelo fue ejecutado o validado.

### 6. QvaPay y facturación
El estado comercial se documenta como **APPROVED** según confirmación del operador. La integración técnica sigue pendiente. Faltan Payment Manager, persistencia de facturas/transacciones, webhook firmado, consulta server-to-server, conciliación, idempotencia, ledger inmutable, créditos, suscripciones, cancelaciones, reembolsos confirmados por documentación oficial y pruebas en sandbox. No realizar cobros reales.

### 7. Privacidad, legal y confianza
Faltan textos legales revisados por asesoría competente, jurisdicción y operador confirmados, política de retención, exportación/eliminación, consentimiento de cookies, inventario de encargados/subencargados, evaluación de SDKs, proceso de incidentes, accesibilidad auditada y datos comerciales verificables. No inventar domicilio, entidad legal, certificaciones, reseñas ni garantías.

### 8. Operación y observabilidad
Faltan CI obligatorio, lint/type checks, cobertura, escaneo de dependencias/SAST/secrets, backups y restauración probada, métricas, trazas, alertas, rate limits, cuotas y runbooks. El endpoint health básico no es monitorización completa.

## Secuencia de cierre propuesta

1. Inventario final de esquema/migraciones y tests; corregir inconsistencias entre tablas legacy y stores nuevos.
2. Autenticación segura, sesiones, membresías, RBAC y pruebas de aislamiento.
3. Conectar el runtime persistente a la API detrás de autorización; mantener las herramientas mutables deshabilitadas hasta validar sandbox y approvals.
4. Crear AXION STUDIO y flujos de usuario/proyecto.
5. Completar Payment Manager/QvaPay en modo de pruebas y ledger.
6. Completar privacidad, accesibilidad, seguridad, CI y observabilidad.
7. Ejecutar pruebas completas en entorno aislado; revisar migraciones y backups.
8. Entregar informe de release con resultados reales. Solo entonces proponer merge y despliegue; ambos requieren aprobación expresa.

## Condiciones que requieren información/decisión del operador

No bloquear el trabajo técnico por estas preguntas: mantener los campos como pendientes hasta el momento en que sean necesarios.
- Nombre legal del operador/entidad y jurisdicción contractual.
- Dirección y datos fiscales/comerciales que deban publicarse.
- Países y edades admitidos, monedas, reglas de impuestos y política de reembolsos.
- Planes, precios, límites de uso y reglas de vencimiento de créditos.
- Política de retención y plazos de eliminación.
- Dominios definitivos de producción y remitente de correo.
- Si AXION puede aplicar cambios locales automáticamente después de aprobación o si cada cambio debe requerir confirmación individual (recomendación: confirmación individual para efectos mutables).

## Criterio de finalización

El proyecto solo podrá etiquetarse como listo cuando las pruebas automatizadas se hayan ejecutado y pasado, el aislamiento multiusuario esté demostrado, el sandbox se haya probado, las integraciones externas se hayan conciliado en modo de pruebas, las migraciones estén revisadas y exista un despliegue aprobado y verificable. La documentación o la existencia de código no sustituyen esas evidencias.
