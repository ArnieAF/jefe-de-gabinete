# F1: tareas pequeñas (propuesta)

Meta de F1 (PLAN sección 6): el agente responde una pregunta usando una herramienta de juguete; cada paso queda registrado; hay 10 evals
que corren con un solo comando y producen un reporte.

Orden: **T1 primero**; después cada tarea cabe en una sesión corta y termina con commit y push (las dependencias están en la tabla).
T1 a T4 y T6 a T9 no dependen del hardware; T5 sí.

Convenciones: Python 3.12; biblioteca estándar más PyYAML y pytest; `dataclasses`. Estados: `pendiente | en curso (rama) | hecha (commit) | bloqueada: motivo`.

## Disposición de archivos (se fija en T1)
- Paquete del harness: `packages/harness/gabinete_harness/`. Paquete de evals: `packages/evals/gabinete_evals/`. Pruebas: `tests/` en la raíz.
- `pyproject.toml`: pytest con `testpaths = ["tests"]` y `pythonpath = ["packages/harness", "packages/evals"]`.
- Para que `python -m gabinete_evals` funcione desde la raíz: instalar con `pip install -e .` (hay que agregar `[build-system]` y la búsqueda de paquetes
  en `pyproject.toml`) o documentar `PYTHONPATH` en el README. Elige uno y **verifícalo ejecutándolo**.
- Archivos de prueba en `.jsonl`: van bajo `tests/` (ahí `.gitignore` sí los versiona).

## Contrato mínimo (no lo cambies sin avisar; la versión larga está en PLAN sección 5)
```python
@dataclass
class ToolCall:     id: str; name: str; arguments: dict
@dataclass
class Message:      role: str                      # "system" | "user" | "assistant" | "tool"
                    content: str = ""
                    tool_calls: list[ToolCall] = field(default_factory=list)
                    tool_call_id: str | None = None
@dataclass
class ToolSpec:     name: str; description: str; schema: dict      # lo que ve el modelo
@dataclass
class Tool:         spec: ToolSpec; fn: Callable[[dict], str]; requires_approval: bool = False
@dataclass
class Usage:        input_tokens: int = 0; output_tokens: int = 0; cost_usd: float = 0.0
@dataclass
class LLMResponse:  text: str | None; tool_calls: list[ToolCall]; usage: Usage

class LLMProvider(Protocol):
    name: str
    def chat(self, messages: list[Message], tools: list[ToolSpec] | None = None, *, max_tokens: int = 1024) -> LLMResponse: ...

@dataclass
class RunResult:    answer: str | None; trajectory: list[ToolCall]; steps: int; cost_usd: float
                    stop_reason: str               # "answer" | "max_steps" | "max_cost" | "denied"
                    run_id: str

def run(task: str, session_id: str, *, provider: LLMProvider, tools: list[Tool],
        approve: Callable[[ToolCall], bool] = deny_all, max_steps: int = 8,
        max_cost_usd: float = 0.0, log_dir: Path | None = None) -> RunResult: ...
```

Formato de un caso de eval con proveedor falso (extiende el de PLAN sección 5):
```yaml
- id: herramienta-eventos-hoy
  capa: herramientas
  guion:                       # solo para ScriptedProvider: sus respuestas, en orden
    - { tool_calls: [{ name: "calendar.list_events", arguments: { date: "2026-11-05" } }] }
    - { text: "Hoy tienes la cita con el dentista y la reunión con Rosa Huamán." }
  pregunta: "¿Qué tengo hoy?"
  esperado:
    contiene: ["dentista", "Rosa"]          # frases clave; sin distinguir mayúsculas ni acentos
    no_contiene: []
    herramienta: "calendar.list_events"     # debe haberse llamado
    max_pasos: 3
  repeticiones: 1
```

## Tareas
| Id | Depende de | Tarea | Está lista cuando | Estado |
|---|---|---|---|---|
| T1 | (ninguna) | Dataclasses y `LLMProvider` del contrato; disposición de archivos y configuración de pytest | `pytest` corre y pasa una prueba que importa los tipos; `python -c "import gabinete_harness"` funciona | pendiente |
| T2 | T1 | `ScriptedProvider`: un `LLMProvider` falso que devuelve las respuestas de un guion, en orden | Pruebas: responde en orden y falla con un error claro si se acaba el guion | pendiente |
| T3 | T1 | Registro de herramientas y herramienta de juguete `calendar.list_events(date)` que lee `fixtures/calendar.json` (solo lectura) | Prueba: los eventos de `2026-11-05` son `cal-008` y `cal-002`, en ese orden | pendiente |
| T4 | T1, T2, T3 | Bucle `run()`: máximo de pasos, aprobación humana obligatoria para herramientas con `requires_approval` (se deniegan por defecto) y registro de eventos en JSONL en `log_dir` (por defecto `evals-out/`; con datos reales debe apuntar **fuera del repo**, variable `GABINETE_LOG_DIR`) | Con `ScriptedProvider`: usa la herramienta y responde; corta al pasar `max_steps`; deniega una herramienta de escritura sin aprobación; el JSONL tiene un evento por paso | pendiente |
| T5 | T1 | Adaptadores `OllamaProvider` y `GeminiProvider`. Verifica sus APIs en la documentación oficial antes de escribirlos; la clave de Gemini sale del entorno o de `.env` | Pruebas con HTTP simulado, y una prueba manual con tu modelo local | pendiente (depende de tu hardware y tu clave) |
| T6 | T1 | Guardián D10: `check_data_policy(provider, notes_dir)` aborta si el proveedor no es `ollama` y la carpeta de notas no está dentro de `fixtures/`; no hay variable para saltárselo | Pruebas: ollama con carpeta real es válido; gemini con carpeta real da error; gemini con `fixtures/` es válido | pendiente |
| T7 | T1 | Runner de evals: lee casos YAML (formato de arriba), repite cada caso N veces, califica por código (`contiene`, `no_contiene`, `herramienta`, `max_pasos`) y escribe un reporte JSON y otro Markdown, comparable con la corrida anterior | Prueba con 2 casos de juguete | pendiente |
| T8 | T2, T4, T7 | 10 evals iniciales en `packages/evals/cases/` (uso de herramienta, permisos, la instrucción inyectada del correo, fechas de hoy), corriendo con `ScriptedProvider` | `python -m gabinete_evals` imprime la tasa de acierto y termina con código 0 | pendiente |
| T9 | T8 | Job de pytest y de los evals deterministas en `.github/workflows/ci.yml` | CI verde en GitHub | pendiente |

Qué miden los evals de T8: con `ScriptedProvider` comprueban el **harness** (permisos, límites, registro), no al modelo. Con un modelo real
(Ollama o Gemini, tras T5) miden al modelo, y ahí aparece la diferencia entre modelos gratuitos y de pago que interesa al proyecto.

Cuando T1 a T9 estén listas y se haya medido con un modelo real, F1 está lista: se actualiza PLAN sección 1 con los números medidos.
