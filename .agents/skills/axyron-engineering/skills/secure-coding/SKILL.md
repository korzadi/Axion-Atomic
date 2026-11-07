---
name: secure-coding
description: Aplica revisión de seguridad durante el diseño y la programación: secretos, autenticación, autorización, validación, aislamiento y dependencias.
---
# Programación segura

Evalúa según el contexto:
- Secretos: no versionar, imprimir, incluir en informes ni enviar al cliente; usar variables de entorno y gestores aprobados.
- Identidad: sesiones seguras, expiración, rotación, CSRF cuando aplique, MFA y recuperación protegida.
- Autorización: denegar por defecto; verificar rol, propietario, proyecto y recurso en servidor.
- Entrada/salida: validación de esquema y tamaño, codificación contextual, consultas parametrizadas y prevención de inyección.
- Archivos: rutas confinadas, límites, MIME, nombres seguros, symlinks y traversal.
- Red: TLS, timeouts, SSRF, allowlists y egress mínimo.
- Datos: minimización, retención, cifrado, aislamiento y borrado autorizado.
- Dependencias: origen, versión fijada, licencia, advisories y superficie añadida.
- Ejecución: no shell arbitrario, privilegios mínimos, límites y sandbox separado.
- Auditoría: eventos útiles sin tokens, contraseñas, claves ni contenido sensible.
No deshabilites MFA, controles, firewall, aislamiento ni validaciones para hacer pasar pruebas. Reporta severidad, evidencia, impacto y mitigación; no declares segura una aplicación por una revisión parcial.
