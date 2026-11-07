# Seguridad y límites conocidos

## Estado actual

AXION ATOMIC dispone de controles implementados en el repositorio, pero **no está certificado ni habilitado para producción pública**. La autenticación web permanece cerrada por defecto mediante `AUTH_ENABLED=false`. Los resultados de CI verifican código y pruebas automatizadas; no prueban la configuración real de SMTP, OAuth, HTTPS, proxy ni cookies en el entorno de despliegue.

## Controles implementados en el código

- Contraseñas con Argon2id y sesiones aleatorias cuyo hash se almacena en la base de datos.
- Cookies de sesión HttpOnly y configuración Secure según entorno.
- Protección CSRF para operaciones autenticadas.
- Tokens de verificación de correo y recuperación de contraseña de un solo uso, almacenados como hashes y con expiración.
- Rate limiting persistente para registro, inicio de sesión y comienzo/callback OAuth; los errores del almacén cierran la operación.
- Los enlaces de verificación y recuperación se reciben en fragmentos URL y el frontend limpia el fragmento del historial antes de enviar el token a la API.
- OAuth Google/GitHub con state de un solo uso, vinculación al navegador y validación de identidad/correo.
- Autorización por proyecto y rol para recursos del workspace.
- Qdrant Cloud mediante endpoint HTTPS; el código rechaza endpoints locales.
- API legacy deshabilitada por defecto y con comparación de clave en tiempo constante cuando se habilita.

## Pendiente antes de producción

- Configurar y probar SMTP real en staging, incluyendo entrega, caducidad, reenvío y manejo de errores.
- Configurar credenciales OAuth fuera del repositorio y verificar callbacks HTTPS definitivos.
- Probar cookies Secure, CSRF, proxy de confianza y sesiones detrás de la infraestructura real. El rate limit usa `request.client.host`; confirmar en staging la IP efectiva del cliente detrás del proxy sin confiar en encabezados `X-Forwarded-*` no validados.
- Completar revisión del rol administrativo global y MFA para operaciones sensibles.

### Controles MFA implementados y controles operativos pendientes

- No almacenar secretos TOTP en texto plano. Cifrarlos en reposo con una clave de aplicación independiente de la base de datos, suministrada por el entorno de ejecución y rotatable.
- Separar el secreto de enrolamiento pendiente del secreto MFA activo; no activar MFA hasta confirmar un código TOTP válido.
- Guardar el último contador TOTP aceptado y rechazar códigos repetidos para impedir replay.
- Generar códigos de recuperación de un solo uso; almacenar únicamente hashes, limitar intentos y registrar su consumo.
- Tras validar contraseña, no emitir cookie/sesión ni completar OAuth hasta superar el desafío MFA cuando la cuenta lo requiera.
- Aplicar rate limiting específico al desafío, auditar enrolamiento, activación, uso de recuperación, desactivación y rotación.
- Diseñar recuperación de acceso y rotación de la clave de cifrado antes de habilitar MFA; si falta la clave o falla el descifrado, denegar el acceso sensible (fail closed).
- Cubrir TOTP expirado, reloj fuera de tolerancia, replay, códigos de recuperación repetidos, concurrencia, revocación de sesiones y fallos de clave con pruebas automatizadas.
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

## Estado MFA actualizado — integración de aplicación completada, operación pendiente

La integración de MFA ya está implementada en el código para los dos caminos de autenticación:

- **Contraseña:** el primer factor se verifica sin crear sesión. Si la cuenta tiene MFA activo, la API devuelve un desafío temporal y no emite cookies de sesión. La sesión se crea únicamente después de validar TOTP o un código de recuperación.
- **Google/GitHub OAuth:** el callback resuelve la identidad y, si la cuenta tiene MFA activo, guarda el desafío en una cookie HttpOnly, Secure según configuración y limitada a la ruta de verificación. No crea sesión hasta validar el segundo factor.
- **Verificación:** los desafíos distinguen login de oauth, expiran a los cinco minutos, limitan intentos y se consumen junto con el contador TOTP o el código de recuperación en transacciones PostgreSQL.
- **Enrolamiento:** existen rutas protegidas por sesión y CSRF para consultar estado, iniciar y confirmar MFA. AXION STUDIO incluye una pantalla de Seguridad para configurar la aplicación TOTP y mostrar los códigos de recuperación una sola vez.
- **Protección de datos:** el secreto TOTP se cifra con AES-256-GCM; PostgreSQL conserva solo ciphertext, nonce y key ID. Los códigos de recuperación tienen 128 bits aleatorios y se almacenan como hashes SHA-256. Las respuestas que entregan secretos/códigos usan Cache-Control: no-store.

### Validación automatizada

El workflow [42324560749](https://github.com/korzadi/Axion-Atomic/actions/runs/42324560749) terminó correctamente en el commit `54451588a88fcfc5c801f3b1aa486876ccee6771`:

- Python: **625 aprobadas, 9 omitidas, 3 advertencias**.
- PostgreSQL migrations e idempotencia: success.
- Qdrant Cloud integration: success.
- AXION STUDIO browser E2E: success.
- Sintaxis JavaScript y compilación Python: success.

Esta ejecución incluye tres pruebas directas de rutas MFA: rechazo de desafío inválido sin crear sesión, creación de sesión solo tras validar el desafío y separación del propósito OAuth.

### Pendientes operativos antes de activar autenticación pública

1. Configurar las variables de MFA en el **entorno runtime del backend**. Los GitHub Actions secrets/variables que ya configuraste no se inyectan automáticamente en el proceso del servidor:
   - AXION_MFA_ENCRYPTION_KEY_ID: identificador no secreto, por ejemplo runtime-v1.
   - AXION_MFA_ENCRYPTION_KEY_B64: clave AES-256 de 32 bytes en Base64. Nunca compartirla por chat ni guardarla en Git.
2. Diseñar y probar rotación multi-clave y recuperación ante pérdida de clave. El proveedor actual resuelve solo la clave activa; no permite descifrar con IDs históricos.
3. Configurar SMTP y OAuth reales en staging y validar los flujos completos desde navegador.
4. Validar proxy HTTPS, cookies Secure, CSRF, recuperación de cuenta, suspensión de usuarios, observabilidad y alertas.
5. Ejecutar revisión independiente de seguridad y aceptación funcional.

**Estado de activación:** mantener AUTH_ENABLED=false. La integración de código y CI no equivale a validación operativa ni autoriza despliegue. No se ha ejecutado migración ni cambio en la base de datos de producción.
