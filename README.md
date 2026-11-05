# Jefe de Gabinete Personal

Agente de IA personal que cada mañana te dice qué pasó, qué sigue y qué recuerda de ti.
Reúne MCP, RAG, memoria (mem0), evals y un harness propio. El plan, las decisiones y el
estado de cada fase están en [PLAN.md](PLAN.md).

**Estado:** fase F0 (preparación). Todavía no hay código del agente.

## Requisitos

- Docker (para PostgreSQL con pgvector).
- Python 3.12 recomendado (la 3.14 no está verificada con mem0 ni LlamaIndex).
- Costo cero: el diseño usa modelos locales o niveles gratuitos (ver PLAN.md, sección 3).

## Arranque de la base de datos

1. Copia `.env.example` a `.env` y define `POSTGRES_PASSWORD` (el archivo `.env` no se sube al repo).
2. `docker compose up -d`
3. `docker compose exec db psql -U gabinete -d gabinete -c "\dx"` debe listar la extensión `vector`.

## Datos de prueba

`fixtures/` contiene notas y un calendario **inventados**. Los evals corren solo sobre esos datos.
Tus notas reales nunca deben ir ahí ni salir de tu máquina.

## Comprobaciones

- `python scripts/verify_fixtures.py` verifica que las notas y el calendario falsos coincidan con
  `fixtures/ground_truth.yaml` (necesita `pip install pyyaml`).
- GitHub Actions (`.github/workflows/ci.yml`) corre esa verificación y además levanta PostgreSQL con
  pgvector con `docker compose`, en cada push o pull request a `main` y `develop`. Los repos privados
  tienen un monto mensual gratis de minutos de Actions; si se agota, los jobs se detienen.

## Estructura

```
.github/    flujo de integración continua
packages/   harness, mcp_servers, rag, memory, evals (vacíos hasta F1)
app/        CLI `gabinete` (vacío hasta F5)
fixtures/   notas y calendario falsos + ground_truth.yaml
scripts/    comprobaciones de los datos de prueba
docker/     scripts de inicio de la base
docs/       resúmenes de auditoría por fase
```
