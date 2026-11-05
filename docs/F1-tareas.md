# F1: tareas pequeñas

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
        max_cost_usd: float = 0.0, log_dir: Path | str | None = None,
        system_prompt: str | None = None) -> RunResult: ...
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

## Detalles fijados por el orquestador (2026-11-05)
- **Importación:** sin instalar nada. pytest usa `pythonpath` (ya configurado en `pyproject.toml`) y `python -m gabinete_evals` se ejecuta con
  `$env:PYTHONPATH = "packages/harness;packages/evals"` (PowerShell).
- **Módulos, para que las tareas no choquen:** `gabinete_harness/types.py` (T1, con `deny_all` y `allow_all`), `providers/scripted.py` (T2),
  `tools/registry.py` y `tools/toy.py` (T3), `policy.py` (T6), `eventlog.py` y `loop.py` (T4), `providers/ollama.py` y
  `providers/gemini.py` (T5); `gabinete_evals/cases.py`, `graders.py`, `suite.py` y `report.py` (T7), `cli.py` y `__main__.py` (T8). Cada tarea escribe sus
  propios archivos y sus pruebas en `tests/test_<tema>.py`. Nadie edita `__init__.py`, `pyproject.toml` ni los módulos de otra tarea: se importa por ruta completa.
- **T2:** el guion es una lista; cada elemento es `{text: str}`, `{tool_calls: [{name, arguments}]}` o un `LLMResponse`. Los `id` de las llamadas se
  generan (`call_1`, `call_2`...). Al agotarse el guion lanza `ScriptExhaustedError` con un mensaje claro. Guarda en `.calls` los mensajes que recibió.
- **T3:** herramientas de juguete: `calendar.list_events(date)` (solo lectura; la fecha local de cada evento es la de su propio desfase horario),
  `notes.read(path)` (solo lectura; solo dentro de `fixtures/vault`: rechaza rutas absolutas, `..` y enlaces simbólicos que salgan) y
  `email.send(to, subject, body)` (`requires_approval=True`; simulada: no envía nada, solo la agrega a una bandeja de salida en memoria).
  Los errores de las herramientas se devuelven como texto JSON `{"error": "..."}`, no como excepciones.
- **T4:** si `approve` devuelve falso para una herramienta con `requires_approval`, esa herramienta NO se ejecuta y la corrida se detiene con
  `stop_reason="denied"` (sin respuesta). `max_cost_usd=0.0` significa sin límite. Si `log_dir` es `None` se usa la variable `GABINETE_LOG_DIR` y,
  si no existe, `evals-out/`. El registro es JSONL: un evento por línea (`run_start`, `model_response`, `tool_call`, `tool_result`, `tool_denied`,
  `run_end`), sin marcas de hora. Una herramienta que falla o un nombre desconocido devuelve un texto `ERROR: ...` al modelo y la corrida sigue.
- **T6:** `check_data_policy(provider_name, notes_dir, repo_root=None)`. Solo `ollama` puede leer fuera de `fixtures/`; cualquier otro nombre
  (incluido `scripted`) se trata como nube. Resuelve `..` y enlaces antes de comparar y lanza `DataPolicyError` indicando el motivo.
- **T7:** el runner recibe una función `execute(caso) -> RunResult` (no conoce `run()` ni los proveedores). Califica `contiene`, `no_contiene`,
  `herramienta`, `max_pasos` y `stop_reason`; escribe `report-<id>.json` y `.md` en una carpeta de salida y compara con el reporte anterior de esa carpeta.
- **T8:** conecta `run()` con `ScriptedProvider`, la CLI (`--cases`, `--out`, `--min-rate`) y 10 casos: eventos de hoy, día sin eventos, leer una nota,
  argumentos inválidos, herramienta desconocida, envío denegado, máximo de pasos, máximo de costo, instrucción inyectada del correo (el modelo
  "vulnerable" intenta `email.send` y el harness lo deniega) y ruta fuera del vault. Termina con código 0 solo si todos pasan. La raíz del repo no se puede cambiar desde la línea de comandos (sería un atajo para el guardián D10).

## Requisitos de las tareas pendientes (T5, T11 y T10)
Orden: **T5 -> T11 -> T10**. T10 (Gemini) es opcional y necesita una clave tuya. Estos requisitos salen de la auditoría de F1: cada uno es una
comprobación que debe quedar cubierta por una prueba. Las APIs (Ollama, Gemini) se verifican en su DOCUMENTACIÓN OFICIAL, no de memoria; anota en el
docstring del módulo la URL que consultaste y la fecha.

**T5: `OllamaProvider`** (`packages/harness/gabinete_harness/providers/ollama.py` y `tests/test_ollama_provider.py`)
1. Solo biblioteca estándar (`urllib.request`); sin dependencias nuevas. Las pruebas NUNCA usan la red.
2. Constructor: `OllamaProvider(model: str, host: str | None = None, *, timeout: float = 60.0, transport=None)`. Si `host` es `None`, usa la variable
   `OLLAMA_HOST` y, si no existe, `http://localhost:11434`. `transport` es una función `(url, payload: dict, timeout: float) -> dict` que se inyecta en las
   pruebas; por defecto hace la petición HTTP real.
3. **`name` es un atributo de la instancia.** Vale exactamente `"ollama"` solo si el host es de este mismo equipo (`localhost`, `127.0.0.1`, `::1`) Y el modelo
   no es un modelo en la nube de Ollama (verifica en la documentación cómo se nombran). En cualquier otro caso vale `"ollama-remoto"`: el guardián D10 solo
   acepta `"ollama"` exacto, así que un Ollama remoto o en la nube cuenta como nube y no puede leer notas reales. Pruebas: host y modelo locales -> `"ollama"`;
   host remoto -> `"ollama-remoto"`; modelo en la nube -> `"ollama-remoto"`; hosts raros (con `usuario@`, IPv6 con corchetes, mayúsculas, `localhost.evil.com`)
   no engañan.
4. Los nombres de herramienta del harness llevan punto (`calendar.list_events`). Si la API no los admite, mapea ida y vuelta con un diccionario y devuelve
   en `ToolCall.name` SIEMPRE el nombre original (el bucle busca por igualdad exacta: un nombre cambiado da "herramienta desconocida"). Prueba: ida y vuelta intacto.
5. Conversión de mensajes: verifica en la documentación cómo representa la API los roles `system`, `user`, `assistant` (con llamadas a herramientas) y `tool`
   (con su resultado). `ToolCall.arguments` siempre es un `dict`; si la API lo devuelve como texto JSON, conviértelo, y si no es JSON válido lanza `ValueError`
   con un mensaje claro. Si la API no da `id` de llamada, genera `call_1`, `call_2`... únicos.
6. Con `tools` vacío (o `None`) NO envíes el campo de herramientas (algunas APIs rechazan la lista vacía).
7. `Usage`: tokens si la API los informa; `cost_usd=0.0`.
8. Errores: si Ollama no responde, lanza un error en español con la pista "¿está corriendo `ollama serve`?"; nunca incluyas en el mensaje el cuerpo de la
   respuesta HTTP ni cabeceras. No leas `.env`.
9. Listo cuando: al menos 3 pruebas con transporte simulado (respuesta de texto, respuesta con llamada a herramienta con nombre mapeado, `tools=[]`), las de `name`,
   de error de conexión y de argumentos inválidos; `pytest` verde y `python scripts/verify_fixtures.py .` verde; y una prueba MANUAL con el modelo local del usuario,
   descrita en el informe (qué modelo, qué comando, qué salió). Si no se pudo hacer, dilo.

**T11: CLI con proveedores reales** (puedes editar `cli.py` y `report.py`; pruebas nuevas en `tests/test_evals_cli_real.py`)
1. `--provider` acepta `scripted` y `ollama` (y `gemini` cuando exista T10); `--model` es obligatorio con un proveedor real; `--ollama-host` es opcional.
2. Con un proveedor real el `guion` de los casos se ignora y no es obligatorio. La aprobación sigue siendo `deny_all`. Los casos de la capa `limites` solo tienen sentido
   con el proveedor de guion: con uno real se omiten y se informa cuántos.
3. El guardián D10 se llama con el `.name` de la INSTANCIA ya creada (no con el de la clase ni con un texto de configuración), antes de leer notas. Sigue sin haber
   forma de saltárselo desde la línea de comandos.
4. Los reportes JSON y Markdown registran `provider` y `model` (sube el formato del reporte si hace falta) y `compare` avisa en `warnings` si el reporte anterior fue
   de otro proveedor o modelo, para no comparar peras con manzanas.
5. Listo cuando: pruebas con un proveedor simulado inyectado (sin red) y `python -m gabinete_evals --provider ollama --model <modelo> --out <carpeta temporal>`
   imprime la tasa de acierto con el modelo local del usuario (prueba manual descrita en el informe).

**T10: `GeminiProvider`** (`providers/gemini.py`, solo si el usuario tiene una clave gratuita de Google AI Studio)
1. `name = "gemini"`. La clave sale SOLO de la variable de entorno `GEMINI_API_KEY` (nunca de `.env`, nunca de un argumento que se registre).
2. **La clave va en una cabecera, jamás en la URL** (verifica el nombre de la cabecera en la documentación). Los errores HTTP se relanzan con un mensaje propio, sin la
   URL ni el cuerpo de la respuesta. Prueba: un error con la clave dentro no la deja pasar al registro ni a los reportes.
3. Mismas reglas de nombres de herramienta, roles, `arguments` y lista vacía que T5. Los esquemas del harness llevan `additionalProperties: false`: verifica si la API
   lo acepta y, si no, quítalo al traducir.
4. El nivel gratuito de la API usa el contenido para mejorar los productos de Google (página oficial de precios): por eso el guardián D10 solo lo deja leer `fixtures/`.
   Maneja el límite de peticiones (error 429) con un mensaje claro y pocos reintentos.

## Tareas
| Id | Depende de | Tarea | Está lista cuando | Estado |
|---|---|---|---|---|
| T1 | (ninguna) | Dataclasses y `LLMProvider` del contrato; disposición de archivos y configuración de pytest | `pytest` corre y pasa una prueba que importa los tipos; con `PYTHONPATH` definido, `python -c "import gabinete_harness"` funciona | hecha |
| T2 | T1 | `ScriptedProvider`: un `LLMProvider` falso que devuelve las respuestas de un guion, en orden | Pruebas: responde en orden y falla con un error claro si se acaba el guion | hecha (merge 50dd866) |
| T3 | T1 | Registro de herramientas y herramienta de juguete `calendar.list_events(date)` que lee `fixtures/calendar.json` (solo lectura) | Prueba: los eventos de `2026-11-05` son `cal-008` y `cal-002`, en ese orden | hecha (merge 3982955) |
| T4 | T1, T2, T3 | Bucle `run()`: máximo de pasos, aprobación humana obligatoria para herramientas con `requires_approval` (se deniegan por defecto) y registro de eventos en JSONL en `log_dir` (por defecto `evals-out/`; con datos reales debe apuntar **fuera del repo**, variable `GABINETE_LOG_DIR`) | Con `ScriptedProvider`: usa la herramienta y responde; corta al pasar `max_steps`; deniega una herramienta de escritura sin aprobación; el JSONL tiene un evento por paso | hecha (merge 7925163) |
| T5 | T1, T4 | Adaptador `OllamaProvider` (`providers/ollama.py`). Requisitos obligatorios en la sección de arriba | Pruebas con transporte simulado (sin Ollama) y una prueba manual con tu modelo local | pendiente |
| T6 | T1 | Guardián D10: `check_data_policy(provider, notes_dir)` aborta si el proveedor no es `ollama` y la carpeta de notas no está dentro de `fixtures/`; no hay variable para saltárselo | Pruebas: ollama con carpeta real es válido; gemini con carpeta real da error; gemini con `fixtures/` es válido | hecha (merge 00a1650) |
| T7 | T1 | Runner de evals: lee casos YAML (formato de arriba), repite cada caso N veces, califica por código (`contiene`, `no_contiene`, `herramienta`, `max_pasos`) y escribe un reporte JSON y otro Markdown, comparable con la corrida anterior | Prueba con 2 casos de juguete | hecha (merge 0581199) |
| T8 | T2, T4, T7 | 10 evals iniciales en `packages/evals/cases/` (uso de herramienta, permisos, la instrucción inyectada del correo, fechas de hoy), corriendo con `ScriptedProvider` | `python -m gabinete_evals` imprime la tasa de acierto y termina con código 0 | hecha (merge 3468e64) |
| T9 | T8 | Job de pytest y de los evals deterministas en `.github/workflows/ci.yml` | CI verde en GitHub | hecha (PR #2) |
| T11 | T5, T7, T8 | CLI con proveedores reales (`--provider`, `--model`) y reportes que registran proveedor y modelo. Requisitos arriba | `python -m gabinete_evals --provider ollama --model <modelo>` imprime la tasa con tu modelo local | pendiente |
| T10 | T5, T11 | Adaptador `GeminiProvider` (opcional; necesita una clave tuya gratuita). Requisitos arriba | Pruebas con transporte simulado; la clave nunca aparece en registros ni reportes | pendiente |

Qué miden los evals de T8: con `ScriptedProvider` comprueban el **harness** (permisos, límites, registro), no al modelo. Con un modelo real
(Ollama o Gemini, tras T5) miden al modelo, y ahí aparece la diferencia entre modelos gratuitos y de pago que interesa al proyecto.

Cuando T1 a T9 y T11 estén listas y se haya medido con un modelo real, F1 está lista: se actualiza PLAN sección 1 con los números medidos.
