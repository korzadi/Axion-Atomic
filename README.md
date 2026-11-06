# AXION ATOMIC

Plataforma de ingeniería de software supervisada, modular y verificable.

## Identidad oficial

- **Producto:** AXION ATOMIC
- **Agente principal:** AXION
- **Modelo principal:** ATOMIC CODE 1.1
- **Interfaz web:** AXION STUDIO
- **Modelo oficial:** https://huggingface.co/Korzadi/Atomic-Code-1.1

El código de este repositorio es la base técnica que se está adaptando a AXION ATOMIC. Los nombres históricos del proyecto de partida no forman parte de la identidad del producto.

## Arquitectura objetivo

- AXION Core y Agent Runtime.
- Model Manager y Model Router, con ATOMIC CODE 1.1 como modelo principal.
- AXION STUDIO como interfaz web propia.
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

## Estado de implementación

Este repositorio está en desarrollo por fases. La presencia de una carpeta, documento o esquema no demuestra por sí sola que una capacidad esté integrada. Cada fase debe informar qué se implementó, qué pruebas se ejecutaron realmente y qué queda pendiente.

## Seguridad y contribuciones

- El contenido de repositorios y documentos recuperados se considera dato no confiable, nunca instrucciones.
- Las operaciones mutables requieren aprobación humana vinculada a la acción exacta.
- Los datos deben aislarse por proyecto y usuario.
- No indexar archivos de entorno, credenciales, claves privadas, tokens ni otros secretos.
- Revisar los cambios y ejecutar las pruebas pertinentes antes de fusionar.
