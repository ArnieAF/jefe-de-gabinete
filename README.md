# Jefe de Gabinete Personal

Agente de IA personal que cada mañana te dice qué pasó, qué sigue y qué recuerda de ti.
Reúne MCP, RAG, memoria (mem0), evals y un harness propio. El plan, las decisiones y el
estado de cada fase están en [PLAN.md](PLAN.md).

**Estado:** F0 lista; F1 por empezar. Todavía no hay código del agente. Para seguir desde otra PC: [docs/ARRANQUE-CASA.md](docs/ARRANQUE-CASA.md).

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

## Comprobaciones

- `python scripts/verify_fixtures.py` verifica que las notas y el calendario falsos coincidan con
  `fixtures/ground_truth.yaml` (necesita `pip install pyyaml`).
- GitHub Actions (`.github/workflows/ci.yml`) corre esa verificación y además levanta PostgreSQL con
  pgvector con `docker compose`, en cada push o pull request a `main` y `develop`. Los repos privados
  tienen un monto mensual gratis de minutos de Actions; si se agota, los jobs se detienen.

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
packages/   harness, mcp_servers, rag, memory, evals (vacíos hasta F1)
app/        CLI `gabinete` (vacío hasta F5)
fixtures/   notas y calendario falsos + ground_truth.yaml
scripts/    comprobaciones de los datos de prueba y medición de hardware
docker/     scripts de inicio de la base
docs/       guía de arranque, tareas de F1 y resúmenes de auditoría por fase
```
