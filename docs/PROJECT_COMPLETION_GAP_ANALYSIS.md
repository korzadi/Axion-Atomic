# Estado real del proyecto AXION ATOMIC

**Rama revisada:** `main`  
**Estado:** desarrollo/hardening; NO apto para producción.  
**Alcance:** inspección estática del repositorio y cambios de código/documentación mediante GitHub. No se ejecutaron pruebas localmente, contenedores, migraciones ni despliegues. La CI del commit `c4e72b7` terminó correctamente; los commits posteriores deben verificarse por separado.

## Identidad y restricciones confirmadas

- Producto: AXION ATOMIC.
- Agente: AXION.
- Modelo objetivo: ATOMIC CODE 1.1.
- Interfaz propia: AXION STUDIO.
- Ollama existente se trata como servicio externo; no instalar, actualizar ni alterar sus datos.
- No se integra ni depende de Open WebUI.
- No se accede al VPS, no se despliega, no se ejecutan migraciones ni se modifican secretos.
- El trabajo de implementación continúa sobre `main), sin operaciones de infraestructura.

## Implementado (inspección estática; validación de ejecución pendiente)

- Filtro de recuperación Qdrant por `project_id` y validación de ese identificador.
- API key con fallo cerrado cuando no existe o es débil, y comparación de tiempo constante.
- GitManager con preview de archivos untracked, selección explícita de rutas y detección de patrones de secretos.
- Persistencia de ejecuciones/acciones y protección contra reutilizar el mismo hash con una carga útil distinta.
- Actualización condicional de aprobaciones y expiración.
- Health endpoint que consulta PostgreSQL, Ollama y Qdrant.
- Dockerfile copia los módulos internos requeridos y mantiene las migraciones como operación administrativa explícita.
- Contrato y estado comercial/técnico QvaPay documentados. El estado comercial se describe como APPROVED según confirmación del operador; la integración técnica sigue pendiente.
- Autenticación web con sesiones, cookies HttpOnly, CSRF, membresías de proyecto y roles de proyecto; permanece cerrada por defecto mediante `AUTH_ENABLED=false`.
- AXION STUDIO dispone de shell web público, formulario de login/registro y navegación de workspace.
- La vista Proyectos usa las rutas autenticadas reales para listar y crear proyectos; el backend asigna el rol owner al creador.
- FastAPI monta `frontend/` en la ruta raíz mediante `StaticFiles`, después de las rutas API. El Dockerfile copia el directorio frontend a la imagen. La entrega real empaquetada aún necesita verificación de CI/build y prueba en entorno autorizado.

## Bloqueadores y riesgos antes de producción

### 1. Identidad, sesiones y autorización multiusuario

El backend contiene autenticación web y autorización por membresía de proyecto, pero el interruptor global sigue deshabilitado. No se debe habilitar hasta completar verificación de correo, controles antiabuso y pruebas negativas de aislamiento. No existe todavía verificación/envío de correo, recuperación de contraseña, MFA ni rate limiting distribuido confirmado. OAuth Google/GitHub no está implementado. Una API key global identifica al servicio, no a una persona, por lo que las rutas legacy `/v1/*` no deben exponerse como API multiusuario.

### 2. AXION STUDIO y entrega

El frontend ya existe como archivo estático `frontend/index.html` y ahora está conectado al servidor FastAPI y al Dockerfile. Esto corrige la brecha previa en la que el archivo no se servía ni se empaquetaba. Aún falta verificar mediante CI y prueba de imagen que la ruta raíz se entregue correctamente en el artefacto final. Los módulos Chat, Modelos, Agentes, Atomic Code, Atomic Video y Conocimiento siguen siendo principalmente vistas informativas; no declarar sus flujos operativos. Administración no tiene API global ni RBAC superadmin verificado.

### 3. Agente, ejecuciones y aprobaciones

Las rutas `/workspace/agent/tasks` todavía crean un plan y una aprobación; esto no demuestra ejecución de herramientas. Existen rutas de lectura de ejecuciones persistidas y decisiones de aprobación, pero el ciclo de vida completo del `CodingAgent`/runtime —inicio, restauración, reanudación, cancelación, reconciliación y entrega de resultados— debe verificarse y conectarse de forma explícita. No afirmar ejecución real desde la API mientras no exista evidencia end-to-end. Las aprobaciones deben seguir vinculadas a payload/hash, proyecto, actor autorizado y expiración.

### 4. Aislamiento y sandbox

El aislamiento RAG por proyecto no reemplaza autorización. Falta demostrar que workspace, Git y sandbox siempre derivan el proyecto del usuario autenticado. Revisar el backend real del sandbox y verificar límites de CPU/RAM/tiempo/tamaño, políticas de red, cuotas y protección contra traversal, symlinks y escape. Mantener herramientas mutables deshabilitadas hasta validar el aislamiento en entorno separado.

### 5. Modelo

La configuración de Ollama apunta a un nombre de modelo, pero no se ha verificado desde esta rama que el servicio cargue ATOMIC CODE 1.1 ni que tokenizer/contexto/plantilla sean compatibles. Falta prueba de inferencia, evaluación reproducible, límites de contexto, cancelación, streaming y selección de modelos. No afirmar que el modelo fue ejecutado o validado. Ollama se mantiene externo y no debe modificarse en esta fase.

### 6. QvaPay y facturación

El estado comercial se documenta como **APPROVED** según confirmación del operador. La integración técnica sigue pendiente: Payment Manager, persistencia de facturas/transacciones, webhook firmado, consulta server-to-server, conciliación, idempotencia, ledger inmutable, créditos, suscripciones, cancelaciones, reembolsos y pruebas en sandbox. No realizar cobros reales ni alterar cuentas de pago.

### 7. Privacidad, legal y confianza

Faltan textos legales revisados por asesoría competente, jurisdicción y operador confirmados, política de retención, exportación/eliminación, consentimiento de cookies, inventario de encargados/subencargados, evaluación de SDKs, proceso de incidentes, accesibilidad auditada y datos comerciales verificables. No inventar domicilio, entidad legal, certificaciones, reseñas ni garantías.

### 8. Operación y observabilidad

El health endpoint básico no equivale a monitorización completa. Faltan escaneo de dependencias/SAST/secrets, cobertura y calidad frontend, backups y restauración probada, métricas, trazas, alertas, rate limits, cuotas y runbooks. La CI de Python que pasó para `c4e72b7` no demuestra que los cambios posteriores de frontend/Dockerfile hayan pasado; comprobar el run más reciente antes de cerrar esta fase.

## Secuencia de trabajo recomendada

1. Confirmar CI de los commits de integración de AXION STUDIO y corregir cualquier fallo de pruebas.
2. Verificar la entrega estática de la página raíz y la precedencia de rutas API con pruebas automatizadas.
3. Completar seguridad de identidad: correo, recuperación, rate limiting y pruebas de sesión/CSRF; mantener auth cerrada mientras tanto.
4. Completar aislamiento multiusuario/proyecto en RAG, Git, sandbox y almacenamiento de ejecuciones.
5. Conectar el runtime persistente del agente y el ciclo de aprobaciones con pruebas end-to-end, manteniendo ejecución mutable bajo aprobación explícita.
6. Conectar módulos de AXION STUDIO progresivamente a APIs reales; implementar roles globales antes del panel administrativo.
7. Completar Payment Manager/QvaPay en modo de pruebas y ledger.
8. Completar privacidad, accesibilidad, seguridad, CI y observabilidad.
9. Revisar migraciones y backups en un entorno aislado; realizar despliegue únicamente con aprobación expresa.
10. Entregar informe de release con resultados verificables. La existencia de código o documentación no sustituye las pruebas ni la aprobación de despliegue.

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

El proyecto solo podrá etiquetarse como listo cuando las pruebas automatizadas se hayan ejecutado y pasado para el commit de release, el aislamiento multiusuario esté demostrado, el sandbox se haya probado, las integraciones externas se hayan conciliado en modo de pruebas, las migraciones estén revisadas y exista un despliegue aprobado y verificable. La documentación o la existencia de código no sustituyen esas evidencias.
