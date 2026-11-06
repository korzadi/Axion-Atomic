# Escalabilidad, protección de capacidad y RCache

## Objetivo y límite honesto

AXION ATOMIC no debe aceptar trabajo ilimitado ni permitir que una ráfaga de usuarios agote la RAM, las conexiones PostgreSQL o el runtime Ollama. La primera instalación prevista utiliza un VPS con CPU y un modelo local de 7B: no puede garantizar 10, 100 o 1000 inferencias simultáneas. La meta inicial es mantenerse estable, procesar una cantidad acotada y rechazar el exceso con respuestas controladas.

## Controles incorporados en código

- **Admisión Ollama:** un turno pesado simultáneo por defecto, ocho solicitudes esperando y un tiempo máximo de cola de 20 segundos. El resto recibe HTTP 503 con `Retry-After`; no se crea una cola ilimitada en memoria.
- **Concurrencia HTTP:** Uvicorn limita a 64 conexiones concurrentes y backlog 128. El exceso puede recibir 503 en el servidor ASGI.
- **PostgreSQL:** pool por proceso de 5 conexiones, máximo 5 conexiones extra y timeout de adquisición de 10 segundos. Con varias réplicas, el total debe calcularse como `réplicas × (pool_size + max_overflow)` y mantenerse por debajo del presupuesto PostgreSQL.
- **Redis:** servicio interno limitado a 192 MB, política LRU y sin persistencia porque se utiliza solo como caché reconstruible.
- **RCache del bot:** guarda embeddings derivados por hash de modelo, dimensión y texto, con TTL configurable (1 hora por defecto). No almacena prompts completos, respuestas del modelo, sesiones, saldo ni eventos de cobro.
- **Fallo de Redis:** la caché es fail-open; si Redis no responde, la consulta continúa contra Ollama. La salud general sí marca dependencia degradada cuando la caché está habilitada.
- **Modelo y memoria:** la concurrencia de inferencia no debe aumentarse sin medir RAM, swap, CPU, latencia y carga real de Atomic Code y del modelo de embeddings.

## RCache: límites deliberados

No se cachean respuestas del chat. De esa forma no se mezclan conversaciones entre usuarios/proyectos ni se evita accidentalmente el futuro registro de consumo y facturación. Una caché de respuestas requerirá política explícita de privacidad, aislamiento user+project, invalidación y tratamiento de cobro por cache hit.

## Qué significa 10 / 100 / 1000 usuarios

| Usuarios simultáneos | Comportamiento objetivo del primer perfil |
|---|---|
| 10 | Hasta 1 inferencia activa y 8 en cola; exceso rechazado de forma controlada. La latencia depende del modelo y del prompt. |
| 100 | La API limita conexiones y la admisión de Ollama evita 100 inferencias concurrentes; muchos usuarios recibirán 503/429 hasta reintentar. |
| 1000 | No es una meta de inferencias servidas por un único VPS CPU. Se espera rechazo controlado y health-check disponible; para atenderlos se requiere separar API y workers, varias máquinas GPU, cola persistente y semáforo distribuido. |

Los números anteriores describen límites configurados, no resultados de un benchmark ni garantía de disponibilidad. El script `load-tests/axion-capacity.js` permite medir en un entorno de staging autenticado con k6. No se ejecutó contra el VPS ni contra usuarios reales.

## Próximas fases de escalado

1. Ejecutar carga escalonada de 10, 100 y 1000 VUs en staging, recogiendo p50/p95/p99, throughput, 429/503, errores 5xx, CPU, RAM, swap, PostgreSQL y Redis.
2. Medir tiempos de inferencia con prompts cortos y largos y determinar la capacidad real del hardware.
3. Si se añaden réplicas API, reemplazar el gate local por un semáforo distribuido Redis con leases, renovación y recuperación de workers.
4. Separar API HTTP y workers de inferencia con cola persistente, límites por usuario/proyecto y cancelación.
5. Añadir métricas Prometheus/OpenTelemetry y alertas de cola, memoria, conexiones y errores.
6. Ajustar pool PostgreSQL y límites de Qdrant/Redis a partir de mediciones, no de suposiciones.

## Estado operativo

Los cambios son código y configuración versionada. No se ha construido ni iniciado Docker, no se ha desplegado nada y no se ha accedido al VPS. El servicio Redis descrito aquí no está instalado ni activo hasta un despliegue autorizado.
