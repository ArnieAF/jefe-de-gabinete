"""Registro de herramientas del harness (tarea T3).

Guarda las herramientas por nombre, conserva el orden de registro y entrega al modelo solo sus `ToolSpec`.
"""
from __future__ import annotations

from typing import Iterable

from gabinete_harness.types import Tool, ToolSpec


class ToolRegistry:
    """Colección ordenada de herramientas con nombres únicos."""

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        """Agrega una herramienta. Lanza `ValueError` si el nombre ya existe y `TypeError` si no es un `Tool`."""
        if not isinstance(tool, Tool):
            raise TypeError(f"se esperaba un Tool, no {type(tool).__name__}")
        name = tool.spec.name
        if not isinstance(name, str) or not name.strip():
            raise ValueError("el nombre de la herramienta debe ser un texto no vacío")
        if name in self._tools:
            raise ValueError(f"ya existe una herramienta registrada con el nombre {name!r}")
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        """Devuelve la herramienta con ese nombre, o `None` si no existe (también si `name` no es texto)."""
        if not isinstance(name, str):
            return None
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        """Las especificaciones, en orden de registro (es lo único que ve el modelo)."""
        return [tool.spec for tool in self._tools.values()]

    def names(self) -> list[str]:
        """Los nombres, en orden de registro."""
        return list(self._tools)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
