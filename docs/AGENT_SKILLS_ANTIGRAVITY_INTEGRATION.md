# AXYRON Agent Skills y compatibilidad con Google Antigravity

## Objetivo

AXYRON adopta el estándar abierto Agent Skills para reutilizar workflows especializados con formato `SKILL.md`. Esto permite compartir skills entre AXYRON y herramientas compatibles como Google Antigravity, sin convertir Antigravity en una dependencia del runtime ni ejecutar código de terceros.

Referencias oficiales:
- Google Antigravity — Agent Skills: https://antigravity.google/docs/skills
- Estándar abierto: https://agentskills.io
- Vercel Skills CLI: https://github.com/vercel-labs/skills

## Pack de ingeniería de Addy Osmani

Pack identificado: https://github.com/addyosmani/agent-skills

La versión consultada declara **25 skills: 24 workflows de ingeniería y una meta-skill**. Incluye definición de requisitos, especificaciones, planificación, implementación incremental, TDD, revisión, seguridad, depuración, CI/CD, documentación, rendimiento, observabilidad y lanzamiento.

Licencia upstream: MIT. AXYRON debe conservar el aviso de copyright y la licencia cuando distribuya copias del contenido original.

### Incorporarlo a un workspace

Para descargar el pack completo y conservar también sus referencias compartidas, desde la raíz del proyecto donde AXYRON trabaja:

```bash
bash scripts/install_agent_skills.sh
```

El instalador fija el upstream en el commit `301b02b12bff98e4688e6984af6556802322bbde`, verifica que existan las 25 skills y conserva `LICENSE` y la carpeta compartida `references/`. Se detiene si el destino ya existe; nunca sobrescribe una instalación anterior.

El runtime AXYRON descubre tanto skills individuales en `.agents/skills/<skill>/SKILL.md` como bundles completos en `.agents/skills/<pack>/skills/<skill>/SKILL.md`. La carpeta `.agents/skills` es también la ubicación de workspace documentada por Antigravity.

Para Antigravity CLI/App, la instalación nativa opcional del plugin upstream es:

```bash
agy plugin install https://github.com/addyosmani/agent-skills.git
agy plugin list
```

No ejecutar estos comandos automáticamente desde el backend de AXYRON. La instalación es una decisión del operador del workspace.

Alternativa mediante el CLI comunitario de skills: revisar primero la lista y luego instalar con copia local, no enlaces simbólicos, para que el runtime de AXYRON pueda validar los archivos:

```bash
npx skills add addyosmani/agent-skills --list
npx skills add addyosmani/agent-skills --skill '*' -a antigravity --copy
```

El pack upstream evoluciona; para producción, fijar un tag o commit revisado en vez de seguir `main` automáticamente. Revisar los cambios antes de actualizar.

## Integración en el runtime de AXYRON

Implementado en esta rama:
- Descubrimiento de `.agents/skills` y compatibilidad histórica con `.agent/skills`.
- Soporte de skills sueltas y bundles con subdirectorio `skills/`.
- Lectura de metadatos `name` y `description` del frontmatter YAML.
- Herramientas de solo lectura `list_skills` y `read_skill` para que AXYRON seleccione y cargue una skill bajo demanda.
- Límites de 100 skills, 64 KB por manifiesto y 20.000 caracteres por skill cargada.
- Rechazo de symlinks, nombres inválidos, manifiestos mal formados y contenido que excede límites.
- No se ejecutan scripts, comandos, hooks ni binarios incluidos en una skill.

Las skills son guías de procedimiento, no permisos. No pueden anular las instrucciones principales de AXYRON, el aislamiento de proyecto, las aprobaciones humanas ni las políticas de seguridad. Las operaciones mutables continúan pasando por las herramientas existentes y sus aprobaciones.

## Estado y límites

- El runtime ya puede descubrir y leer skills instaladas en el workspace.
- El pack upstream de 25 skills está identificado y documentado, pero **no está copiado ni instalado automáticamente dentro de este repositorio**. La instalación requiere que el operador decida qué workspace debe recibirlo.
- La compatibilidad de formato con Antigravity no significa que AXYRON ejecute Antigravity, use su modelo, comparta credenciales o controle su IDE.
- El runtime HTTP de AXYRON sigue sin tener conectado el backend Docker aislado; estas skills no habilitan terminal ni ejecución arbitraria.
- No declarar skills instaladas hasta que existan los archivos y las pruebas de descubrimiento confirmen su presencia.
