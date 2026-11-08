# Guía de usuario — AXYRON STUDIO

Axyron Studio es la interfaz web de AXYRON ATOMIC. Esta guía describe solo lo que funciona hoy; las capacidades anunciadas como «Próxima actualización» dentro de la interfaz no están disponibles todavía.

## Requisitos para el usuario

- Una URL de acceso válida proporcionada por el administrador (HTTPS).
- Una cuenta verificada por correo electrónico.
- Recomendado: una aplicación autenticadora (Google Authenticator, Aegis, etc.) para MFA.

> El operador de la instancia controla si el registro está abierto. Si `AUTH_ENABLED` no está habilitado o SMTP no está operativo, no podrás registrarte ni recuperar contraseña: solicita el acceso al administrador.

## Crear una cuenta y entrar

1. Abre la página principal y elige **Crear cuenta**.
2. Rellena correo, contraseña y acepta los términos. La contraseña debe cumplir la política de la plataforma.
3. Revisa tu correo y abre el enlace de **verificación**. Sin verificar, la cuenta no puede iniciar sesión.
4. Inicia sesión. Si tu cuenta tiene MFA activo, introduce el código de 6 dígitos de tu aplicación autenticadora.
5. Para cerrar sesión, usa el botón de salida; la sesión se revoca y las cookies se eliminan.

## Seguridad de la cuenta

- **MFA:** en el primer inicio, o desde **Ajustes/Cuenta**, puedes enrolar tu cuenta: escanea el código, confirma el primer código y guarda los códigos de recuperación en un lugar seguro. MFA protege el inicio de sesión y las operaciones administrativas.
- **Recuperación de contraseña:** usa «Olvidé mi contraseña». El enlace de recuperación es de un único uso y caduca; todas las sesiones abiertas se revocan al restablecer.
- **OAuth:** si el administrador configuró Google o GitHub OAuth, puedes iniciar sesión con ese proveedor; si MFA está activo, se solicitará el segundo factor igualmente.

## Proyectos y trabajo

- **Proyectos:** desde Studio creas y abres proyectos. Cada proyecto aísla sus datos; solo sus miembros acceden a su contenido. Los permisos por proyecto son: propietario, administrador, editor y lector.
- **Atomic Code:** el chat usa el modelo Atomic Code 1.1 del servidor. No hay streaming: la respuesta completa aparece al final de la generación. El historial del proyecto queda guardado en la plataforma.
- **Conocimiento:** puedes indexar texto o cargar documentos PDF, DOCX, TXT o Markdown (máx. 5 MB por archivo). La plataforma extrae el texto, lo trocea y lo indexa por proyecto. Los archivos con secretos o demasiado grandes se rechazan. El chat no inventa respuestas si no hay material suficiente: te lo indicará.
- **Agente Axyron:** el agente analiza tu objetivo y propone cambios. **Nada se aplica sin tu aprobación explícita**: verás las acciones propuestas, podrás aprobarlas o rechazarlas (propietario/administrador). Las acciones aprobadas se ejecutan de forma auditada; las acciones interrumpidas requieren una reconciliación manual («marcar aplicada» o «marcar no aplicada»).
- **Consumo:** muestra las solicitudes y tokens medidos en tu proyecto. La medición está en modo informativo; no se cobra nada desde la interfaz.

## Facturación

- Verás tu **saldo de créditos** y el **historial de movimientos del ledger** si la plataforma te asignó cuotas o lotes.
- El **catálogo** es «informativo»: no se muestran precios ni paquetes que el servidor no haya publicado, y el checkout permanece deshabilitado. La compra y la acreditación automática por QvaPay no están operativas; cuando lo estén, usarán Lightning Address con conciliación del lado del servidor.
- Si eres administrador con rol `billing_manage`, la sección **Operaciones de créditos y facturación** del portal administrativo permite recuperar liquidaciones, conciliar reservas sin ejecución y revertir consumos liquidados, todo con motivo auditable y confirmaciones; no hay borrado del historial.

## Administración (solo roles asignados)

En `https://admin.axyronatomic.com` (si el operador lo expone): gestión de cuentas (búsqueda, concesión/revocación de roles globales, activar/deshabilitar), registro de auditoría, visión agregada de facturación e invoices QvaPay, y tus propios datos de acceso. Todas las mutaciones exigen CSRF, confirmaciones y quedan auditadas. No puedes deshabilitar tu propia cuenta ni revocar al último administrador activo.

## Privacidad y límites

- Las sesiones son opacas y se revocan al cerrar sesión; las cookies son HttpOnly y las mutaciones exigen token anti-CSRF.
- Los documentos indexados en Conocimiento están acotados por proyecto; tu cuenta no puede listar ni borrar fuentes de otro proyecto.
- La telemetría de inferencia no almacena prompts ni respuestas; solo mediciones (tokens, modelo, proyecto).
- Los PDF escaneados sin texto extraíble no tienen OCR y pueden rechazarse.

## Qué no está disponible todavía

- Checkout, precios y paquetes comerciales públicos.
- Pagos reales por QvaPay (integración en evaluación; checkout deshabilitado).
- Plugins, conectores OAuth, Skills Hub, MCP (roadmap).
- Streaming de respuestas, generación de vídeo/imagen/audio.
- Exportación de datos personales y eliminación de cuenta desde la interfaz.
- OCR de documentos escaneados.

## Ayuda

Si algo no funciona (verificación de correo, MFA, permisos de un proyecto, checkout ausente), solicita ayuda al administrador de tu instancia indicando la URL, la hora y el mensaje de error exacto. No compartas contraseñas, códigos MFA, tokens ni sesiones.
