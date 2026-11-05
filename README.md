# Jefe de Gabinete Personal

[![CI](https://github.com/ArnieAF/jefe-de-gabinete/actions/workflows/ci.yml/badge.svg)](https://github.com/ArnieAF/jefe-de-gabinete/actions/workflows/ci.yml)

Objetivo: un agente de IA personal que cada mañana te diga qué pasó, qué sigue y qué recuerda de ti, con MCP, RAG, memoria (mem0), evals
y un harness propio. Se construye por fases: **hoy existen el harness** (bucle con aprobación humana, herramientas de juguete, guardián de
privacidad y registro de eventos) **y los evals**; MCP, RAG y memoria llegan en F2 a F4. El plan, las decisiones y el estado de cada fase
están en [PLAN.md](PLAN.md).

**Estado:** F1 en curso. El núcleo del harness (tipos, proveedor de prueba, herramientas, bucle con aprobación humana, guardián de privacidad y
runner de evals) ya tiene pruebas; todavía no usa un modelo real. Detalle en [PLAN.md](PLAN.md) y [docs/F1-tareas.md](docs/F1-tareas.md).
Para seguir desde otra PC: [docs/ARRANQUE-CASA.md](docs/ARRANQUE-CASA.md).

## Requisitos

- Git.
- Docker Desktop para PostgreSQL con pgvector (en Windows usa WSL2; su consumo de RAM no está medido).
  Si Docker no corre bien en tu PC, el plan B está en PLAN.md, sección 9, fila "Docker Desktop pesado" (sin verificar).
- Python 3.12: con la que se desarrolla y corre el CI; ninguna otra versión está probada (la 3.14 no está verificada con mem0 ni LlamaIndex).
- Ollama para los modelos locales: se documenta en F1, cuando exista el adaptador de proveedor.
- Costo cero: el diseño usa modelos locales o niveles gratuitos (ver PLAN.md, sección 3). Los proveedores
  en nube solo reciben los datos falsos de `fixtures/` (regla D10).

## Arranque de la base de datos

1. Copia `.env.example` a `.env` (PowerShell: `Copy-Item .env.example .env`; bash: `cp .env.example .env`) y define
   `POSTGRES_PASSWORD`, sin caracteres `$` ni comillas. El archivo `.env` no se sube al repo.
2. `docker compose up -d --wait`
3. `docker compose exec db psql -U gabinete -d gabinete -c "\dx"` debe listar la extensión `vector`.
4. Para apagarla: `docker compose stop`. No se reinicia sola al abrir Docker Desktop.

## Datos de prueba

`fixtures/` contiene notas y un calendario **inventados**. Los evals corren solo sobre esos datos.
Tus notas reales nunca deben ir ahí ni salir de tu máquina.

## Evals

Los 10 evals iniciales usan un proveedor de guion fijo: comprueban el **harness** (permisos, límites, registro), no a un modelo. Con modelos reales
(Ollama, Gemini) llegan en las tareas T5, T10 y T11 de [docs/F1-tareas.md](docs/F1-tareas.md).

```powershell
$env:PYTHONPATH = "packages/harness;packages/evals"
python -m gabinete_evals --out "$env:TEMP\evals-out"
```

```bash
PYTHONPATH=packages/harness:packages/evals python -m gabinete_evals --out /tmp/evals-out
```

Imprime la tasa de acierto y escribe un reporte JSON y otro Markdown (y lo compara con la corrida anterior). Códigos de salida: 0 = aprobado,
1 = por debajo de `--min-rate`, 2 = error de uso o de configuración. El guardián de privacidad D10 corre antes que cualquier caso.

## Comprobaciones

- `python scripts/verify_fixtures.py` verifica que las notas y el calendario falsos coincidan con
  `fixtures/ground_truth.yaml` (necesita `pip install pyyaml`).
- GitHub Actions (`.github/workflows/ci.yml`) corre esa verificación, levanta PostgreSQL con pgvector con
  `docker compose` y ejecuta `pytest` y los evals en Linux y Windows, en cada push o pull request a `main` y `develop`. Al ser un repositorio
  público, los ejecutores estándar de GitHub Actions no tienen costo.

## Pruebas

```powershell
pip install pyyaml pytest
pytest
```

El código no se instala: pytest encuentra `packages/harness` y `packages/evals` por la configuración de `pyproject.toml`. Para ejecutar
algo con `python -m` desde la raíz (por ejemplo `python -m gabinete_evals`), define antes
`$env:PYTHONPATH = "packages/harness;packages/evals"` (PowerShell) o `PYTHONPATH=packages/harness:packages/evals` (bash).

## Estructura

```
AGENTS.md   instrucciones para asistentes de IA (Antigravity, etc.)
.github/    flujo de integración continua
packages/   harness y evals (F1, con pruebas); mcp_servers, rag y memory (vacíos hasta F2 a F4)
app/        CLI `gabinete` (vacío hasta F5)
fixtures/   notas y calendario falsos + ground_truth.yaml
scripts/    comprobaciones de los datos de prueba y medición de hardware
docker/     scripts de inicio de la base
docs/       guía de arranque, tareas de F1 y resúmenes de auditoría por fase
```

## Licencia

[MIT](LICENSE) © 2026 Arnie Adriano.
