# Instrucciones para asistentes de IA (Antigravity, Claude Code u otros)

Proyecto: **Jefe de Gabinete Personal** (agente de IA con MCP, RAG, memoria y evals). Responde en español.
Fuente de verdad: `PLAN.md` (lee las secciones 1, 5 y 6; el resto solo si hace falta). Si no coincide con el código, avisa.

## Reglas que no se negocian
1. **Secretos:** nunca pidas, escribas ni muestres contraseñas, tokens o claves, y no abras ni leas `.env`, ni imprimas las variables de entorno (`env`, `Get-ChildItem Env:`). Solo se edita `.env.example`. Las claves las pone el usuario (en `.env` o en variables de entorno).
2. **Datos reales (D10):** las notas, correos y calendario reales NO se leen, abren, copian al repo ni pegan en este chat. Viven fuera del repo y solo los procesa el programa local con un modelo local (ollama). Tú trabajas solo con `fixtures/` (datos falsos).
3. **Nada destructivo sin que el usuario lo pida:** no borres volúmenes (`docker compose down -v`), ramas remotas ni archivos ajenos, y no cambies la visibilidad del repo (es público).
4. **Distingue** verificado (lo ejecutaste y viste la salida) / revisado a mano / sospechado. No digas que algo funciona sin ejecutarlo. Las APIs de librerías y modelos se verifican en su documentación oficial, no de memoria.
5. **Costo cero:** no agregues servicios ni dependencias de pago.

## Flujo de git
- `main` = solo lo que el usuario probó: no hagas push ni merge a `main`.
- Trabaja en `feat/*` o `fix/*` desde `develop`. **Haz `git push -u origin <rama>` después de cada commit**: si se acaban los tokens, no se pierde nada.
- Antes de unir a `develop` ejecuta `python scripts/verify_fixtures.py .`, `pytest` y los evals (`$env:PYTHONPATH = "packages/harness;packages/evals"; python -m gabinete_evals --out "$env:TEMP\evals-out"`). Si algo falla, **no unas**: deja la rama subida y marca la tarea `bloqueada: <el error>`.
- Si todo pasa, une a `develop` con `--no-ff` y sube `develop`. Si trabajas solo, tú integras a `develop`; nunca a `main`.
- Commits pequeños, en español.

## Cómo seguir
- Tareas: `docs/F1-tareas.md`. Estados: `pendiente | en curso (rama) | hecha (commit) | bloqueada: motivo`. Actualiza el estado en el mismo commit final de la tarea.
- Guía para el usuario: `docs/ARRANQUE-CASA.md`.
