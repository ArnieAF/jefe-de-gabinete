# Revisión del paquete de traspaso a la PC de casa

Fecha: 2026-11-05 · Rama revisada: `docs/traspaso-casa` (con los cambios sin commitear) · Revisor: un agente `rol-auditor` pedido con `model: 'fable'`

## Qué se revisó
`AGENTS.md`, `docs/ARRANQUE-CASA.md`, `docs/F1-tareas.md`, `scripts/hardware.ps1` y las ediciones de `PLAN.md`, `README.md` y `.gitignore`,
con tres lentes: corrección (comandos, enlaces, coherencia de las tareas), seguridad y datos, y claridad para un modelo con pocos tokens.
Un solo revisor y sin escéptico adicional: es una revisión ligera de documentos, no el cierre de una fase.

## Qué encontró (10 hallazgos) y qué se hizo

| # | Sev. | Hallazgo | Decisión |
|---|---|---|---|
| 1 | alto | El paquete estaba sin commitear; la guía asume que `git clone` lo trae | **Resuelto**: commit, integración a `develop` y push (se comprueba con `git log origin/develop -- AGENTS.md`) |
| 2 | medio | T4, T7 y T8 necesitaban campos que el contrato no definía (proveedor, herramientas, aprobación, guion del proveedor falso) | **Corregido**: contrato mínimo y formato de eval ampliado en `docs/F1-tareas.md`; `PLAN.md` sección 5 lo enlaza |
| 3 | medio | Los paquetes no eran importables ni se sabía dónde van las pruebas; `*.jsonl` ignorado | **Corregido**: disposición de archivos y pytest en T1; excepción `!tests/**/*.jsonl`. Si se usa `pip install -e .` o `PYTHONPATH` se decide y verifica en T1 |
| 4 | medio (sospechado) | `.env` dentro de la carpeta que abre el IDE; `.gitignore` no protege del IDE | **Corregido en parte**: regla de no abrir `.env`, contraseña desechable, clave de Gemini como variable de entorno. Que Antigravity respete `.gitignore` o permita excluir archivos **no se pudo verificar** |
| 5 | medio | Sin estados definidos ni qué hacer si fallan las pruebas o se acaban los tokens | **Corregido** en `AGENTS.md` (estados, push tras cada commit, no unir si falla) |
| 6 | bajo | `up -d` seguido de `exec` puede fallar si la base aún arranca | **Corregido**: `--wait` en README y guía |
| 7 | bajo | Sin entorno virtual ni pytest en la guía | **Corregido** |
| 8 | bajo | Contradicciones menores (quién integra, D10, "independiente") | **Corregido**: `PLAN.md` sección 8, estado de D10 y columna "Depende de" |
| 9 | bajo | Casos límite de `hardware.ps1` (alias de Python de la Microsoft Store, otros discos, acento) | **Corregido** |
| 10 | bajo | El mensaje para pegar hacía leer todo `PLAN.md` | **Corregido**: secciones 1, 5 y 6, y anotar el hardware en el plan |

Añadido a raíz del hallazgo: los registros de ejecuciones con datos reales deben ir fuera del repo (`GABINETE_LOG_DIR`, tarea T4).

## Qué respalda estas afirmaciones
- **Ejecutado por mí después de corregir:** el analizador de PowerShell sobre `scripts/hardware.ps1` (0 errores) y su ejecución (sin usuario ni rutas),
  el ejemplo YAML del contrato leído con PyYAML, `git check-ignore` sobre los patrones nuevos, `scripts/verify_fixtures.py` y el tamaño de `AGENTS.md` (2117 bytes).
- **Afirmado por el revisor:** los comandos de solo lectura que dice haber ejecutado. No hubo escéptico independiente.
- **Lo que dicen los términos de Antigravity** (guía, sección 5) viene de sus páginas oficiales, consultadas el 2026-11-05; el revisor no pudo verificarlo.

## Qué no tiene registro
- **Ninguna prueba dentro de Antigravity:** que lea `AGENTS.md` está confirmado solo por su documentación, no se probó. Tampoco se probaron el mensaje para pegar ni el comportamiento de un modelo gratuito con estas instrucciones.
- **El modelo real del revisor**: solo consta el parámetro pedido al lanzarlo.
- **La transcripción del revisor** está en la carpeta de sesión de Claude Code de la computadora donde se hizo la revisión, no en el repositorio.
