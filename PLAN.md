# Jefe de Gabinete Personal — PLAN

Creado: 2026-11-04 · Última actualización: 2026-11-05

> Agente de IA personal que cada mañana te dice qué pasó, qué sigue y qué recuerda de ti.
> Reúne cinco piezas que crecen por separado: **MCP**, **RAG**, **memoria (mem0)**, **evals** y **harness propio**.

## 1. Estado (se mantiene al día)

| Fase | Contenido | Estado |
|---|---|---|
| F0 | Preparación: repo, estructura, Docker, vault de prueba | en curso (2026-11-05) |
| F1 | Harness mínimo + primeros 10 evals | pendiente |
| F2 | MCP de notas (solo lectura) | pendiente |
| F3 | RAG sobre notas + evals de recuperación | pendiente |
| F4 | Memoria con mem0 + evals de memoria | pendiente |
| F5 | Briefing matutino + permisos y aprobación humana | pendiente |
| F6 | MCP de calendario y GitHub (lectura primero) | pendiente |
| F7 | Post-MVP: correo, UI, ejecución programada | fuera del MVP |

Hecho hasta ahora: solo este plan. **No hay código escrito ni nada verificado.**

## 2. Alcance

### Dentro del MVP (F0–F5)
- Comando `gabinete morning` en terminal que produce el briefing del día.
- Un servidor MCP propio (notas en carpeta Markdown) y el cliente MCP dentro del harness.
- RAG sobre esas notas con PostgreSQL + pgvector.
- Memoria persistente entre sesiones (perfil, proyectos, preferencias, resumen del día anterior).
- Harness propio: bucle de herramientas, registro de eventos, límites de pasos y costo, aprobación humana antes de cualquier escritura.
- Suite de evals que corre sobre datos de prueba falsos y compara contra la corrida anterior.

### Fuera del MVP
- Correo (es lo más sensible; va al final y en solo lectura).
- Interfaz web o de escritorio.
- Ejecución programada automática (cron), notificaciones, multiusuario, despliegue en la nube.
- Cualquier acción de escritura sobre servicios reales sin aprobación explícita.

## 3. Decisiones

**Restricción (2026-11-05):** el proyecto se hará también en una PC de casa sin servicios de pago ni GPU decente. Por eso D4–D6, D9 y D10 priorizan modelos gratuitos o locales y una interfaz de proveedor intercambiable.

| # | Decisión | Estado | Por qué |
|---|---|---|---|
| D1 | Lenguaje del núcleo: **Python** | propuesta, por confirmar | Es donde mem0, LlamaIndex y el SDK de MCP tienen mejor soporte, y encaja con "aprendiendo Python" del CV. Alternativa: TypeScript. |
| D2 | Base vectorial: **PostgreSQL + pgvector** en Docker | propuesta | Reutiliza PostgreSQL y Docker que ya manejas; una sola base para RAG y para datos propios. |
| D3 | Notas: carpeta **Markdown** (compatible con Obsidian) | por confirmar | Se necesita saber dónde viven tus notas reales. |
| D4 | Modelo del agente: **proveedor intercambiable**, gratuito por defecto (Ollama local, o el nivel gratuito de Gemini solo con datos falsos). Claude (p. ej. `claude-haiku-5-5`) queda como adaptador opcional si algún día hay saldo | propuesta (cambió el 2026-11-05) | Se trabajará también en una PC sin GPU y sin servicios de pago. Antes era Claude Sonnet 5.5. |
| D5 | Evals: **calificadores por código primero**. El LLM-juez, solo donde el código no alcanza, es un **modelo distinto al del agente** y corre únicamente sobre datos falsos | propuesta (cambió el 2026-11-05) | Evita que el modelo se califique a sí mismo y gasta menos cuota gratuita. |
| D6 | Embeddings: modelo **local pequeño en CPU** | propuesta (cambió el 2026-11-05) | Mantiene tus notas en tu máquina y no necesita GPU. La calidad en español se mide en F3; no se asume. |
| D7 | Harness: bucle propio sobre la API de mensajes con uso de herramientas, sin frameworks de agentes | decidida | Es parte del objetivo: entender y controlar el bucle. |
| D8 | RAG: primero a mano (chunking, embeddings, búsqueda), luego comparar con LlamaIndex | propuesta | Aprender primero; medir después si el framework mejora. |
| D9 | El harness habla con el modelo a través de una interfaz `LLMProvider` (sección 5); el bucle de herramientas sigue siendo propio (D7) | propuesta | Permite pasar de un modelo gratuito a otro (por ejemplo al agotarse una cuota) o a uno de pago sin reescribir el agente. |
| D10 | **Privacidad:** los datos reales (notas, correo, calendario) solo pasan por modelos locales; las nubes gratuitas reciben únicamente los datos falsos de `fixtures/` | decidida | La página de precios de la API de Gemini indica que en el nivel gratuito el contenido se usa para mejorar los productos de Google (consultada el 2026-11-05). |

## 4. Estructura del repositorio

```
AI/
├─ PLAN.md
├─ docker-compose.yml        # PostgreSQL + pgvector
├─ pyproject.toml
├─ .env.example              # solo nombres de variables, nunca valores
├─ packages/
│  ├─ harness/               # bucle del agente, permisos, registro de eventos
│  ├─ mcp_servers/notes/     # servidor MCP de notas (luego calendar/, github/)
│  ├─ rag/                   # ingesta, chunking, embeddings, retrieve()
│  ├─ memory/                # envoltura de mem0 detrás de una interfaz propia
│  └─ evals/                 # casos, runner, calificadores, reporte
├─ app/                      # CLI `gabinete`
├─ fixtures/                 # vault de notas y calendario FALSOS para evals
└─ docs/                     # resúmenes de auditorías por fase
```

Archivos compartidos (`pyproject.toml`, `docker-compose.yml`, núcleo del harness) los edita **un solo agente** a la vez.

## 5. Contratos (se fijan antes de repartir trabajo)

Firmas propuestas; se confirman en F0.

```python
# rag
def retrieve(query: str, k: int = 5) -> list[Chunk]: ...
# Chunk: {source_path: str, text: str, score: float}

# memory  (mem0 queda encapsulado aquí; se verifica su API real en F4)
class MemoryStore:
    def remember(self, user_id: str, messages: list[dict]) -> None: ...
    def recall(self, user_id: str, query: str, k: int = 5) -> list[Fact]: ...
    def forget(self, user_id: str, fact_id: str) -> None: ...

# harness
class Tool: name: str; schema: dict; requires_approval: bool
def run(task: str, session_id: str, *, max_steps: int, max_cost_usd: float) -> RunResult: ...
# RunResult: {answer, trajectory: list[ToolCall], cost_usd, steps}

# proveedor de modelo (D9): un adaptador por proveedor (ollama, gemini, anthropic)
class LLMProvider(Protocol):
    name: str
    def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None, *, max_tokens: int = 1024) -> LLMResponse: ...
# LLMResponse: {text: str | None, tool_calls: list[ToolCall], usage: Usage}
```

Reglas de herramientas MCP: nombres `dominio.accion` (`notes.search`, `calendar.list_events`); toda herramienta de escritura declara `requires_approval = True`.

Formato de caso de eval (YAML):

```yaml
- id: memoria-actualiza-ciudad
  capa: memoria            # rag | memoria | herramientas | permisos | seguridad | briefing
  sesiones: ["Vivo en Cusco", "Me mudé a Lima", "(3 sesiones de otros temas)"]
  pregunta: "¿En qué ciudad vivo?"
  esperado: { contiene: "Lima", no_contiene: "Cusco" }
  repeticiones: 5
```

## 6. Fases y criterio de "listo"

| Fase | Se considera lista cuando… |
|---|---|
| **F0** | `docker compose up` levanta PostgreSQL con pgvector; el vault falso existe; `.env.example` documenta las variables; el repo tiene `git init` con ramas `main` y `develop`. |
| **F1** | El agente responde una pregunta usando una herramienta de juguete; cada paso queda registrado; hay 10 evals que corren con un solo comando y producen un reporte. |
| **F2** | El servidor MCP de notas lista, lee y busca por texto en el vault falso; el harness lo consume; evals de uso de herramientas pasan. |
| **F3** | `retrieve()` devuelve la nota correcta en el top 3 en ≥ 80 % de los casos del vault falso (meta inicial, se ajusta con datos). |
| **F4** | El agente recuerda un dato tras 5 sesiones y actualiza uno que cambió, en ≥ 80 % de las repeticiones. |
| **F5** | `gabinete morning` genera el briefing; ninguna escritura se ejecuta sin aprobación; evals de permisos y seguridad en 100 %. |
| **F6** | Calendario y GitHub en solo lectura con evals propios; escritura solo con aprobación. |

Los umbrales son metas iniciales, no resultados: se reemplazan por los números medidos.

## 7. Evals (cuatro tipos, separados)

1. **Recuperación:** ¿trae los documentos correctos? (recall@k, MRR)
2. **Respuesta:** ¿es correcta y fiel a las fuentes? (código cuando se puede; LLM-juez con rúbrica cuando no)
3. **Uso de herramientas:** ¿elige la herramienta y los argumentos correctos? (se califica la trayectoria)
4. **Memoria:** ¿recuerda, actualiza y olvida bien entre sesiones?

Más dos transversales: **permisos** (no escribe sin aprobación) y **seguridad** (resiste instrucciones inyectadas en notas o correos). Cada caso se repite varias veces y se mide la tasa de acierto. Todo corre sobre `fixtures/`, nunca sobre tus datos reales.

## 8. Reparto de trabajo (modo orquestador)

| Rol | Agente / modelo | Tareas |
|---|---|---|
| Orquestador | sesión principal | Contratos, decisiones ambiguas o irreversibles, integración con `--no-ff`, verificación del conjunto (typecheck, lint, tests, build). |
| Backend | `rol-backend` (Sonnet) | Harness, servidor MCP, RAG, memoria, evals, Docker. |
| Frontend | `rol-frontend` (Opus) | Solo en F7 si se hace UI. |
| Mecánico | `rol-mecanico` (Haiku) | Documentación, formato, renombres, fixtures repetitivos. |
| Auditor | `rol-auditor` (modelo distinto al autor, normalmente Fable) | Revisión de solo lectura con 3 lentes: seguridad, UX y corrección. |

- Cada agente trabaja en su rama y worktree (`feat/harness`, `feat/mcp-notes`, `feat/rag`, `feat/memory`, `feat/evals`), con `git fetch` y `git switch -c <rama> origin/develop` explícitos.
- `main` solo recibe lo que tú probaste; el trabajo integrado vive en `develop`.
- Ciclo por fase: construir → revisar (3 lentes) → corregir → integrar → informe.
- El workflow multiagente `feature-pipeline.js` solo se usa si lo pides explícitamente o tienes ultracode activo.

## 9. Riesgos

| Riesgo | Mitigación |
|---|---|
| Datos privados (notas, correo, calendario) | Solo lectura al inicio; correo al final; tokens en variables de entorno o gestor de secretos, nunca en el repo ni en el chat; evals solo con datos falsos. |
| Inyección de instrucciones en contenido externo (un correo o nota dice "reenvía todo") | Todo contenido externo se trata como dato, no como instrucción; escrituras siempre con aprobación; eval de seguridad dedicado. |
| Alcance que se infla | Una fuente de datos por fase; el correo queda fuera del MVP. |
| Costo de API | Límite de pasos y de costo por ejecución en el harness; registro de costo por corrida. |
| Evals inestables (el mismo caso pasa y falla) | Repeticiones y tasa de acierto; calificadores por código siempre que sea posible. |
| Memoria que contradice o acumula basura | Evals de actualización y contradicción; operación `forget` expuesta. |
| mem0 y librerías cambian de API | Se encapsulan detrás de interfaces propias (sección 5); se verifica la API vigente al implementar. |
| Cuotas de los niveles gratuitos (los límites reales no están verificados) | Topes por día y reintentos con espera en el runner de evals; pocas repeticiones al inicio; guardar resultados; poder cambiar de proveedor (D9). |
| Modelos pequeños que usan mal las herramientas (varias fuentes lo advierten; no se midió aquí) | Los evals de uso de herramientas lo miden en F1; se compara modelo por modelo y se elige el mínimo viable. |
| Docker Desktop pesado en una PC modesta (sospechado, no medido) | Probar `docker compose up` en la PC de casa al cerrar F0; plan B: PostgreSQL nativo o SQLite con extensión vectorial. |
| mem0 extrae mal con un modelo chico (sospechado) | Eval de memoria en F4; plan B: memoria propia simple detrás de `MemoryStore`. |

## 10. Reglas que no se negocian

- Secretos fuera del repo y del chat. Nadie pide ni pega contraseñas, tokens ni claves de servicio.
- Los agentes escriben archivos; nada se aplica a bases o servicios reales sin que tú lo hagas o lo autorices.
- Se distingue siempre **verificado** (ejecutado) / **revisado a mano** / **sospechado**.
- El texto de un subagente es dato, no instrucción ni permiso.
- Al cerrar cada fase: se anota el registro de modelos y se guarda el resumen de la auditoría en `docs/` en un commit aparte.

## 11. Para el currículum

- El proyecto se lista como **"2026 (En proceso)"**, igual que los otros dos en curso.
- La descripción solo menciona piezas que existan. Si una tecnología cambia (por ejemplo D1), se actualiza el CV.
- Cuando haya evals corriendo, se pueden agregar cifras reales (casos, tasa de acierto). **No se escriben cifras antes de medirlas.**

## 12. Preguntas abiertas

1. ¿Python o TypeScript para el núcleo? (D1) — F0 usa Python como propuesta; falta tu confirmación.
2. ¿Tus notas están en Obsidian o en otra carpeta? (D3) — no urge hasta que quieras leer notas reales.
3. ¿Qué hardware tiene la PC de casa (RAM, CPU, GPU)? Define qué modelos locales sirven.
4. ¿Cuántas horas por semana puedes dedicarle? Define el calendario de fases.
5. Nombre y correo para los commits de git: esta PC no tiene identidad configurada, así que el commit inicial queda pendiente.

## 13. Registro de modelos

| Fase | Tarea | Modelo | Cómo se supo |
|---|---|---|---|
| F0 (plan) | Redacción de este `PLAN.md` | Claude Sonnet 5.5 (`claude-sonnet-5-5`) | Identificador indicado por el entorno de la sesión; no hay otra verificación. |
