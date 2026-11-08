# Mantenimiento manual del rate limiter

auth_rate_limit_buckets conserva contadores de ventanas temporales para limitar abuso. Los registros con expires_at <= now ya no participan en ventanas activas y pueden limpiarse por lotes.

## Herramienta

scripts/prune_expired_rate_limits.py ofrece dos modos:

- **Predeterminado (dry-run):** solo cuenta registros expirados; no ejecuta DELETE.
- **Aplicación explícita:** --apply invoca una sola vez prune_expired_rate_limits y elimina como máximo el tamaño del lote indicado.

Ejemplo de inspección:

```bash
python3 scripts/prune_expired_rate_limits.py
```

Ejemplo de un lote explícito:

```bash
python3 scripts/prune_expired_rate_limits.py --apply --batch-size 500
```

El tamaño permitido es de 1 a 10.000 y el valor predeterminado es 1.000. Cada ejecución de aplicación elimina un solo lote; para continuar, el operador debe revisar el resultado y volver a ejecutar deliberadamente la herramienta. No hay scheduler ni ejecución automática en el arranque o en las solicitudes HTTP.

## Límites de seguridad

- Ejecutar solo con acceso administrativo a la base de datos correcta y dentro de una ventana de mantenimiento aprobada.
- No imprime claves de bucket, subjects, emails, IPs, URLs ni configuración.
- No altera usuarios, sesiones, tokens de recuperación ni otros datos.
- No modifica ni reinicializa la base de datos; elimina exclusivamente filas expiradas de auth_rate_limit_buckets.
- La tarea no autoriza despliegues ni cambios en VPS/producción. La ejecución real queda bajo control del operador.
