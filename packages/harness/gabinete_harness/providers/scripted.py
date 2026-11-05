"""ScriptedProvider: un LLMProvider falso que devuelve las respuestas de un guion, en orden.

Sirve para probar el harness (bucle, permisos, límites, registro) sin red ni modelo real. Cada elemento del
guion es un `LLMResponse` (se devuelve tal cual) o un dict con las claves `text`, `tool_calls` y `usage`.
El guion se valida entero al construir el proveedor, para que un error de tipeo falle pronto y no a mitad
de una corrida.
"""
from __future__ import annotations

import copy
import math
from collections.abc import Sequence
from dataclasses import dataclass

from gabinete_harness.types import LLMResponse, Message, ToolCall, ToolSpec, Usage

_RESPONSE_KEYS = ("text", "tool_calls", "usage")
_TOOL_CALL_KEYS = ("name", "arguments", "id")
_USAGE_KEYS = ("input_tokens", "output_tokens", "cost_usd")


class ScriptExhaustedError(Exception):
    """Se llamó a `chat()` cuando ya no quedaban respuestas en el guion."""


@dataclass
class RecordedCall:
    """Lo que vio el "modelo" en una llamada a `chat()`: una copia de los mensajes, los nombres de las
    herramientas ofrecidas (lista vacía si no se ofreció ninguna) y `max_tokens`."""

    messages: list[Message]
    tool_names: list[str]
    max_tokens: int


def _bad(index: int, detail: str) -> ValueError:
    return ValueError(f"guion[{index}]: {detail}")


def _check_keys(index: int, where: str, data: dict, allowed: tuple[str, ...]) -> None:
    unknown = sorted(str(k) for k in data if k not in allowed)
    if unknown:
        raise _bad(index, f"{where} tiene claves desconocidas {unknown}; las permitidas son {list(allowed)}")


def _parse_usage(index: int, raw: object) -> Usage:
    """Convierte el `usage` del guion (dict) en `Usage`; `None` equivale a ceros."""
    if raw is None:
        return Usage()
    if not isinstance(raw, dict):
        raise _bad(index, f"`usage` debe ser un dict, no {type(raw).__name__}")
    _check_keys(index, "`usage`", raw, _USAGE_KEYS)
    for key in ("input_tokens", "output_tokens"):
        value = raw.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise _bad(index, f"`usage.{key}` debe ser un entero >= 0, no {value!r}")
    cost = raw.get("cost_usd", 0.0)
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
        raise _bad(index, f"`usage.cost_usd` debe ser un número finito >= 0, no {cost!r}")
    return Usage(
        input_tokens=raw.get("input_tokens", 0),
        output_tokens=raw.get("output_tokens", 0),
        cost_usd=float(cost),
    )


def _parse_tool_call(index: int, j: int, raw: object, explicit_ids: dict[str, str]) -> ToolCall:
    """Convierte una llamada del guion en `ToolCall`. Si no trae `id`, queda con `id=""` y el proveedor
    se lo asigna después (así los ids generados no chocan con los explícitos)."""
    where = f"`tool_calls[{j}]`"
    if not isinstance(raw, dict):
        raise _bad(index, f"{where} debe ser un dict con `name`, `arguments` e `id` opcional, no {type(raw).__name__}")
    _check_keys(index, where, raw, _TOOL_CALL_KEYS)
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise _bad(index, f"{where} necesita `name` (texto no vacío); recibió {name!r}")
    arguments = raw.get("arguments", {})
    if not isinstance(arguments, dict):
        raise _bad(index, f"{where}.arguments debe ser un dict, no {type(arguments).__name__}")
    call_id = raw.get("id", "")
    if "id" in raw:
        if not isinstance(call_id, str) or not call_id.strip():
            raise _bad(index, f"{where}.id debe ser un texto no vacío; recibió {call_id!r}")
        if call_id in explicit_ids:
            raise _bad(index, f"{where}.id {call_id!r} ya se usó en {explicit_ids[call_id]}")
        explicit_ids[call_id] = f"guion[{index}].tool_calls[{j}]"
    return ToolCall(id=call_id, name=name, arguments=copy.deepcopy(arguments))


def _parse_response(index: int, raw: dict, explicit_ids: dict[str, str]) -> LLMResponse:
    """Valida un elemento dict del guion y lo convierte en `LLMResponse`."""
    _check_keys(index, "la respuesta", raw, _RESPONSE_KEYS)
    text = raw.get("text")
    if text is not None and not isinstance(text, str):
        raise _bad(index, f"`text` debe ser un texto o None, no {type(text).__name__}")
    raw_calls = raw.get("tool_calls", [])
    if not isinstance(raw_calls, (list, tuple)):
        raise _bad(index, f"`tool_calls` debe ser una lista, no {type(raw_calls).__name__}")
    calls = [_parse_tool_call(index, j, c, explicit_ids) for j, c in enumerate(raw_calls)]
    if text is None and not calls:
        raise _bad(index, "respuesta vacía: debe traer `text` (texto) o `tool_calls` (al menos una llamada)")
    return LLMResponse(text=text, tool_calls=calls, usage=_parse_usage(index, raw.get("usage")))


class ScriptedProvider:
    """LLMProvider falso: devuelve, en orden, las respuestas de un guion.

    Cada elemento del guion es un `LLMResponse` (se devuelve tal cual, sin validar) o un dict:
    `{"text": str | None, "tool_calls": [{"name": str, "arguments": dict, "id": str}], "usage": {...}}`.
    Debe traer `text` o al menos una llamada; `arguments` por defecto es `{}`; `usage` ausente es en ceros.
    Los `id` ausentes se generan por instancia en secuencia (`call_1`, `call_2`...), sin chocar con los
    explícitos. Los ids explícitos de un mismo guion no pueden repetirse.

    `calls` guarda un `RecordedCall` por cada llamada a `chat()` (copia profunda de los mensajes), incluida
    la que falla por guion agotado, para que las pruebas comprueben qué vio el "modelo".
    """

    name = "scripted"

    def __init__(self, script: Sequence[dict | LLMResponse]) -> None:
        if isinstance(script, (str, bytes, dict)) or not isinstance(script, Sequence):
            raise ValueError(f"el guion debe ser una lista de respuestas, no {type(script).__name__}")
        explicit_ids: dict[str, str] = {}
        responses: list[LLMResponse] = []
        pending: list[ToolCall] = []  # llamadas dict sin id, en orden de aparición
        for index, item in enumerate(script):
            if isinstance(item, LLMResponse):
                for call in item.tool_calls:  # se devuelve tal cual; solo se reservan sus ids
                    explicit_ids.setdefault(call.id, f"el LLMResponse de guion[{index}]")
                responses.append(item)
            elif isinstance(item, dict):
                response = _parse_response(index, item, explicit_ids)
                pending.extend(c for c in response.tool_calls if not c.id)
                responses.append(response)
            else:
                raise _bad(index, f"cada elemento debe ser un dict o un LLMResponse, no {type(item).__name__}")
        counter = 0
        for call in pending:
            counter += 1
            while f"call_{counter}" in explicit_ids:
                counter += 1
            call.id = f"call_{counter}"
        self._responses = responses
        self._position = 0
        self.calls: list[RecordedCall] = []

    @property
    def remaining(self) -> int:
        """Cuántas respuestas del guion quedan por devolver."""
        return len(self._responses) - self._position

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        *,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Devuelve la siguiente respuesta del guion; lanza `ScriptExhaustedError` si ya no quedan."""
        self.calls.append(
            RecordedCall(
                messages=copy.deepcopy(list(messages)),
                tool_names=[t.name for t in tools or []],
                max_tokens=max_tokens,
            )
        )
        if self._position >= len(self._responses):
            raise ScriptExhaustedError(
                f"el guion se agotó: tiene {len(self._responses)} respuesta(s) y ya se hicieron "
                f"{len(self.calls)} llamada(s) a chat(), incluida esta; no hay respuesta para ella"
            )
        response = self._responses[self._position]
        self._position += 1
        return response
