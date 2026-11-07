---
name: git-workflow
description: Gestiona cambios Git con commits claros, diffs revisados, ramas seguras y sin sobrescribir trabajo ajeno.
---
# Flujo Git seguro

1. Inspecciona rama, estado, diff y últimos commits antes de actuar.
2. No descartes, sobrescribas ni reformatees cambios preexistentes no relacionados.
3. Mantén cambios pequeños y enfocados; revisa staged y unstaged por separado.
4. Nunca incluyas .env, claves, tokens, credenciales, dumps, datos privados o artefactos generados sensibles.
5. No uses force push, reset destructivo, rebase público ni eliminación de ramas sin permiso explícito.
6. No fusiones a main, publiques releases ni cambies configuración de repositorio sin autorización.
7. Escribe mensajes de commit descriptivos; confirma solo los archivos previstos.
8. Tras cambios, inspecciona el diff final y comprueba estado limpio o documenta lo pendiente.
9. No declares CI verde hasta consultar el workflow del SHA exacto y verificar su conclusión.
