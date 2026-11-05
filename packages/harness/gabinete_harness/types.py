"""Tipos del contrato del harness.

Contrato mínimo en docs/F1-tareas.md (versión larga: PLAN.md, sección 5). No cambies estas firmas
sin avisar: las demás tareas de F1 se escriben contra ellas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol, runtime_checkable

ROLES = ("system", "user", "assistant", "tool")
STOP_REASONS = ("answer", "max_steps", "max_cost", "denied")


@dataclass
class ToolCall:
    """Una llamada a herramienta pedida por el modelo."""

    id: str
    name: str
    arguments: dict


@dataclass
class Message:
    """Un mensaje de la conversación. `tool_call_id` solo va en mensajes con rol "tool"."""

    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"rol inválido {self.role!r}; los permitidos son {ROLES}")


@dataclass
class ToolSpec:
    """Lo que ve el modelo de una herramienta: nombre, descripción y esquema JSON de sus argumentos."""

    name: str
    description: str
    schema: dict


@dataclass
class Tool:
    """Una herramienta del harness: su especificación, la función que la ejecuta y si pide aprobación."""

    spec: ToolSpec
    fn: Callable[[dict], str]
    requires_approval: bool = False

    @property
    def name(self) -> str:
        return self.spec.name


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


@runtime_checkable
class LLMProvider(Protocol):
    """Un adaptador por proveedor de modelo (ollama, gemini, anthropic, scripted...)."""

    name: str

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...


@dataclass
class RunResult:
    answer: str | None
    trajectory: list[ToolCall]
    steps: int
    cost_usd: float
    stop_reason: str  # uno de STOP_REASONS
    run_id: str

    def __post_init__(self) -> None:
        if self.stop_reason not in STOP_REASONS:
            raise ValueError(f"stop_reason inválido {self.stop_reason!r}; los permitidos son {STOP_REASONS}")


ApprovalFn = Callable[[ToolCall], bool]


def deny_all(call: ToolCall) -> bool:
    """Aprobación por defecto: no se aprueba nada."""
    return False


def allow_all(call: ToolCall) -> bool:
    """Aprueba todo. Solo para pruebas: nunca como valor por defecto."""
    return True
