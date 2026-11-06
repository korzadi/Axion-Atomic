# Seguridad y límites conocidos

## Estado actual

AXION ATOMIC dispone de controles implementados en el repositorio, pero **no está certificado ni habilitado para producción pública**. La autenticación web permanece cerrada por defecto mediante `AUTH_ENABLED=false`. Los resultados de CI verifican código y pruebas automatizadas; no prueban la configuración real de SMTP, OAuth, HTTPS, proxy ni cookies en el entorno de despliegue.

## Controles implementados en el código

- Contraseñas con Argon2id y sesiones aleatorias cuyo hash se almacena en la base de datos.
- Cookies de sesión HttpOnly y configuración Secure según entorno.
- Protección CSRF para operaciones autenticadas.
- Tokens de verificación de correo y recuperación de contraseña de un solo uso, almacenados como hashes y con expiración.
- Rate limiting persistente para rutas de autenticación; los errores del almacén cierran la operación.
- OAuth Google/GitHub con state de un solo uso, vinculación al navegador y validación de identidad/correo.
- Autorización por proyecto y rol para recursos del workspace.
- Qdrant Cloud mediante endpoint HTTPS; el código rechaza endpoints locales.
- API legacy deshabilitada por defecto y con comparación de clave en tiempo constante cuando se habilita.

## Pendiente antes de producción

- Configurar y probar SMTP real en staging, incluyendo entrega, caducidad, reenvío y manejo de errores.
- Configurar credenciales OAuth fuera del repositorio y verificar callbacks HTTPS definitivos.
- Probar cookies Secure, CSRF, proxy de confianza y sesiones detrás de la infraestructura real.
- Completar revisión del rol administrativo global y MFA para operaciones sensibles.
- Definir monitoreo, alertas, retención y limpieza de tokens/sesiones/rate limits expirados.
- Revisar logs, telemetría y frontend para asegurar que no expongan tokens ni datos sensibles.
- Realizar revisión independiente de seguridad y privacidad y pruebas de abuso.

## Reglas de seguridad

- No habilitar `AUTH_ENABLED` por el mero hecho de que CI esté verde.
- No incluir SMTP/OAuth credentials, API keys, tokens, contraseñas ni claves privadas en Git, logs o mensajes.
- No indexar `.env`, claves privadas, semillas, tokens, volcados de producción ni datos personales.
- Mantener PostgreSQL y servicios internos fuera de exposición pública innecesaria.
- No habilitar ejecución arbitraria de comandos. Antes de ejecutar código se requiere sandbox efímero no privilegiado, cuotas CPU/RAM/tiempo, filesystem aislado y política de red.
- Vincular cualquier aprobación a un hash inmutable de la acción/diff para evitar TOCTOU.
- Tratar salidas del modelo y contenido recuperado por RAG como datos no confiables.
- Los cambios de despliegue, VPS, Docker y datos de producción requieren autorización explícita.
