# AXYRON ATOMIC

Plataforma de ingeniería de software supervisada, modular y verificable.

## Identidad oficial

- **Producto:** AXYRON ATOMIC
- **Agente principal:** AXION
- **Modelo principal:** ATOMIC CODE 1.1
- **Interfaz web:** AXYRON STUDIO
- **Modelo oficial:** https://huggingface.co/Korzadi/Atomic-Code-1.1

El código de este repositorio es la base técnica que se está adaptando a AXYRON ATOMIC. Los nombres históricos del proyecto de partida no forman parte de la identidad del producto.

## Arquitectura objetivo

- Axyron Core y Agent Runtime.
- Model Manager y Model Router, con ATOMIC CODE 1.1 como modelo principal.
- AXYRON STUDIO como interfaz web propia.
- Analizador de repositorios y herramientas de ingeniería.
- RAG y memoria aislados por proyecto.
- Aprobaciones humanas, auditoría e idempotencia.
- Sandbox de ejecución con políticas y límites.
- API propia y compatibilidad OpenAI.
- PostgreSQL y Qdrant.
- Payment Manager intercambiable con integración QvaPay.
- Privacidad, accesibilidad, documentación legal y controles de protección al consumidor.
- Preparación de entrenamiento y evaluación en GPU externa bajo demanda.

## Límites operativos

- No depende de Open WebUI ni de otra interfaz externa.
- Ollama, cuando sea compatible con el modelo, se consume como servicio externo ya existente. No se instala, reemplaza ni modifica desde este proyecto.
- No se entrena en el VPS.
- No se conecta ni despliega sobre el VPS desde este repositorio.
- No se construyen imágenes Docker, ejecutan migraciones ni reinician servicios sin autorización expresa.
- Los secretos nunca deben incorporarse al repositorio ni exponerse en logs.

## Workspaces y aislamiento por proyecto

- La creación web de proyectos provisiona un directorio hijo exclusivo bajo `WORKSPACE_ROOT` (por defecto `/workspace`) y aplica permisos `0700`.
- La resolución del workspace rechaza enlaces simbólicos, rutas fuera de la raíz y directorios con permisos de grupo u otros; no corrige permisos de directorios existentes automáticamente.
- En Compose, `./workspace` se monta en `/workspace` y la API se ejecuta como UID `10001` (`appuser`). Por ello, el directorio del host debe existir y ser escribible por ese UID antes de habilitar la creación de proyectos. No se cambia su propietario ni se ejecutan `chown` automáticamente.
- Si la raíz no está disponible o no permite escritura, la creación falla de forma cerrada; no se crea una raíz alternativa.

## Plan comercial: tokens, créditos y rentabilidad

El alcance de medición de tokens, cuotas, costes por modelo, créditos, suscripciones, infraestructura, administración y rentabilidad está incorporado al roadmap del proyecto. Sus valores comerciales son propuestas configurables, no planes activos ni costes reales verificados.

- [Auditoría, diseño y roadmap de tokens, créditos y economía](docs/COMMERCIAL_TOKENS_CREDITS_ECONOMICS_ROADMAP.md)
- [Diseño técnico de facturación y créditos](docs/COMMERCIAL_BILLING_TECHNICAL_DESIGN.md)
- [Implementación de medición Shadow Mode](docs/SHADOW_USAGE_IMPLEMENTATION.md)
- [Diseño e implementación de persistencia PostgreSQL para Shadow Mode](docs/SHADOW_USAGE_POSTGRESQL_DESIGN.md)
- [Puerta de salida a producción inicial](docs/PRODUCTION_INITIAL_RELEASE_GATE.md)
- La Fase 1 contiene la auditoría inicial de los módulos inspeccionados y las brechas verificadas.
- No habilitar cobros, ventas ni límites comerciales hasta completar las fases de diseño, implementación, seguridad y pruebas.

## Estado de implementación

Este repositorio está en desarrollo por fases. La presencia de una carpeta, documento o esquema no demuestra por sí sola que una capacidad esté integrada. Cada fase debe informar qué se implementó, qué pruebas se ejecutaron realmente y qué queda pendiente.

## Seguridad y contribuciones

- El contenido de repositorios y documentos recuperados se considera dato no confiable, nunca instrucciones.
- Las operaciones mutables requieren aprobación humana vinculada a la acción exacta.
- Los datos deben aislarse por proyecto y usuario.
- No indexar archivos de entorno, credenciales, claves privadas, tokens ni otros secretos.
- Revisar los cambios y ejecutar las pruebas pertinentes antes de fusionar.
