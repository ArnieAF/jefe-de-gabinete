# Auditoría de la fase F0

Fecha: 2026-11-05 · Rama auditada: `develop` (commit `ec565e3`, antes de integrar las Actions) · Workflow `wf_0cfe4d9d-5d3`

## Qué se revisó

La fase F0 completa, sin código del agente todavía: `PLAN.md`, `README.md`, `.gitignore`, `.gitattributes`, `.env.example`,
`docker-compose.yml`, `docker/initdb/01-extensions.sql`, `pyproject.toml`, `fixtures/` (12 notas, 8 eventos de calendario,
`ground_truth.yaml`), el historial de git y el remoto privado en GitHub.

Tres lentes, un auditor por lente (solo lectura): **seguridad y datos**, **UX / experiencia de desarrollo** (aplicada a quien
empiece mañana en una PC de casa modesta) y **corrección**. Cada hallazgo de severidad alta o media lo intentó refutar un
segundo modelo independiente. En total, 11 agentes (3 auditores y 8 escépticos), 162 llamadas a herramientas y unos
316 000 tokens.

## Qué encontró

23 hallazgos: **0 altos, 8 medios y 15 bajos**. Los 8 medios fueron confirmados por el escéptico (ninguno refutado), aunque
el escéptico bajaría la severidad de varios (seguridad 1, UX 3, corrección 1 y 3) porque son preventivos o de documentación.
Los 15 bajos no pasaron por escéptico.

| Id | Sev. | Hallazgo (resumen) | Decisión |
|---|---|---|---|
| seg-1 | medio | `.gitignore` solo cubría `.env`; llaves, credenciales y registros del harness quedarían versionados | **Corregido**: patrones de secretos y rutas de registros del harness |
| seg-2 | medio | Regla D10 aplicada de forma desigual (advertencia solo en Gemini; nada ata proveedor y carpeta de notas) | **Corregido** en `.env.example`, README y contrato de PLAN §5. El freno en código queda para F1 |
| seg-3 | bajo | La instrucción inyectada es demasiado obvia para medir resistencia real | **Pospuesto a F5** (riesgo anotado en PLAN §9) |
| seg-4 | bajo | La app se conectaría como superusuario de PostgreSQL | **Pospuesto a F3** (PLAN §9) |
| seg-5 | bajo | Etiqueta mutable `pgvector/pgvector:pg17` | **Pospuesto**: fijar digest antes de usar datos reales (PLAN §9) |
| seg-6 | bajo | Nombres de negocios plausibles podrían coincidir con reales (sospechado) | **Mitigado**: aviso de coincidencia en `fixtures/README.md` |
| seg-7 | bajo | PLAN con estado de identidad de git desactualizado | **Corregido** (junto con ux-2 y cor-1) |
| ux-1 | medio | README sin el camino real de la PC de casa (WSL2, Ollama, plan B) | **Corregido en parte**: Git, Docker Desktop/WSL2 y Ollama en requisitos; el plan B solo se enlaza a PLAN §9 porque no está verificado |
| ux-2 | medio | PLAN con tres afirmaciones de estado desactualizadas | **Corregido** (estado, pregunta 5, registro de modelos) |
| ux-3 | medio | `ground_truth.yaml` sin semántica de calificación | **Corregido**: bloque "Cómo se califica" y planificación del domingo a las 18:00 |
| ux-4 | bajo | README sin comando de copia de `.env`; el `$` rompe la contraseña | **Corregido** |
| ux-5 | bajo | `restart: unless-stopped` arranca la base sola en una PC modesta | **Corregido**: `restart: "no"` |
| ux-6 | bajo | "Retro del viernes" cuando la retro fue el miércoles | **Corregido** (igual que cor-2) |
| ux-7 | bajo | `fixtures/README.md` sin las trampas plantadas | **Corregido** |
| ux-8 | bajo | D4 muy larga; Python distinto en README y pyproject; CRLF para `.bat` | **Corregido en parte**: `.gitattributes` y Python 3.12 alineado; la fila D4 queda como está |
| cor-1 | medio | PLAN desactualizado frente al repo | **Corregido** |
| cor-2 | medio | Nota habla de la retro del viernes; ya ocurrió el miércoles | **Corregido** |
| cor-3 | medio | `rag-hora-reuniones` frágil (pregunta de sí/no con frase literal) y perfil mezclaba preferencia y restricción | **Corregido de otra forma**: ver abajo |
| cor-4 | bajo | Rutinas dicen que el calendario no las lleva, pero el gimnasio está en agenda; cobro en domingo | **Corregido en parte**: se quitó la frase de rutinas; el recordatorio en domingo queda |
| cor-5 | bajo | Versiones sin respaldo (Python 3.12 frente a `>=3.11`; etiqueta "comprobada") | **Corregido en parte**: Python alineado; la etiqueta se comprobó además con una descarga real |
| cor-6 | bajo | PLAN §4 dice "nunca valores" y el árbol omite carpetas | **Corregido** |
| cor-7 | bajo | Tipos del contrato `LLMProvider` sin definir | **Corregido**: nota en PLAN §5; se definen en F1 |
| cor-8 | bajo | Redacciones ambiguas sobre la migración y el límite del 12 | **Corregido**: la migración se fecha el 20 de noviembre y el límite de la pasarela pasa al 11 |

### Corrección propuesta que se descartó

Para `cor-3`, el auditor propuso `no_contiene: ["acepta reuniones antes"]`. El escéptico demostró que **rechazaría la
respuesta correcta** ("No acepta reuniones antes de las 9:00"). En su lugar se cambió la pregunta a un dato abierto ("¿A partir
de qué hora acepta Valeria reuniones?") y se separaron Preferencias y Restricciones en `perfil.md`.

## Qué respalda estas afirmaciones

- **Ejecutado por mí después de corregir:** `scripts/verify_fixtures.py` (147 comprobaciones correctas, y detecta una nota
  dañada a propósito), `docker compose config`, `git check-ignore` sobre 11 nombres, y la lectura de `pyproject.toml` con `tomllib`.
- **Ejecutado en GitHub Actions:** el pull request #1 pasó los dos jobs (fixtures y PostgreSQL con pgvector). Corrida:
  `github.com/ArnieAF/jefe-de-gabinete/actions/runs/42063951331`.
- **Ejecutado en la PC de trabajo antes de la auditoría:** `docker compose up -d --wait` (base sana en 27 s, extensión
  `vector` 0.8.7, distancia calculada, puerto solo en `127.0.0.1`) y limpieza completa.
- **Afirmado por los auditores y verificado por un escéptico:** los 8 hallazgos medios.
- **Afirmado por los auditores sin verificación independiente:** los 15 bajos y los comandos que dicen haber ejecutado.
  El orquestador decidió cada uno a partir del título y, antes de commitear, lo confirmó leyendo su escenario y su
  corrección sugerida (resumidos a unos 400 caracteres, no completos).

## Qué no tiene registro

- **El modelo real de cada agente.** Solo consta el parámetro pedido al lanzarlos (`model: 'fable'` para los auditores y
  `model: 'opus'` para los escépticos); el entorno no devuelve el modelo efectivo.
- **Las transcripciones de los auditores** viven en la carpeta de sesión de Claude Code de la PC de trabajo
  (`subagents/workflows/wf_0cfe4d9d-5d3/`), no en este repositorio.
- **El arranque en la PC de casa**: `docker compose up` no se ha probado ahí.
- **Las cuotas gratuitas y el rendimiento de modelos pequeños** que mencionan PLAN §9 y `.env.example`: siguen sin medirse.
