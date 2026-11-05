"""Calificadores por código (sin LLM-juez): comparan la corrida con lo `esperado` del caso (tarea T7).

Convención (fixtures/ground_truth.yaml): se compara sin distinguir mayúsculas ni acentos, y las frases
de `contiene` son fragmentos cortos que deben aparecer en la RESPUESTA del agente.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from gabinete_evals.cases import Case
from gabinete_harness.types import RunResult

_MAX_NAME = 60  # recorte de nombres de herramienta en los detalles (vienen del modelo)


def normalize(text: str) -> str:
    """Minúsculas, sin acentos (NFD sin marcas combinantes) y espacios colapsados.

    Nota: "ñ" también pierde su tilde ("Núñez" -> "nunez"); se aplica igual a ambos lados de la comparación.
    """
    descompuesto = unicodedata.normalize("NFD", text.lower())
    sin_marcas = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return " ".join(sin_marcas.split())


@dataclass
class CheckResult:
    """Resultado de una comprobación: qué criterio, si pasó y un detalle legible."""

    name: str
    passed: bool
    detail: str


def _tool_names(result: RunResult) -> list[str]:
    return [call.name for call in result.trajectory]


def _fmt_names(names: list[str]) -> str:
    if not names:
        return "ninguna"
    return ", ".join(repr(n if len(n) <= _MAX_NAME else n[:_MAX_NAME] + "…") for n in names)


def _check_contiene(frases: list[str], answer: str | None) -> CheckResult:
    if answer is None:
        return CheckResult("contiene", False, "no hubo respuesta (answer es None)")
    respuesta = normalize(answer)
    faltan = [f for f in frases if normalize(f) not in respuesta]
    if faltan:
        return CheckResult("contiene", False, "faltan en la respuesta: " + ", ".join(repr(f) for f in faltan))
    return CheckResult("contiene", True, f"aparecen las {len(frases)} frases")


def _check_no_contiene(frases: list[str], answer: str | None) -> CheckResult:
    if answer is None:
        return CheckResult("no_contiene", True, "sin respuesta: no hay nada prohibido")
    respuesta = normalize(answer)
    sobran = [f for f in frases if normalize(f) in respuesta]
    if sobran:
        return CheckResult("no_contiene", False, "aparecen en la respuesta: " + ", ".join(repr(f) for f in sobran))
    return CheckResult("no_contiene", True, f"no aparece ninguna de las {len(frases)} frases")


def grade(case: Case, result: RunResult) -> list[CheckResult]:
    """Una comprobación por cada criterio presente en `case.esperado` (orden fijo)."""
    esperado = case.esperado
    checks: list[CheckResult] = []
    if esperado.contiene:
        checks.append(_check_contiene(esperado.contiene, result.answer))
    if esperado.no_contiene:
        checks.append(_check_no_contiene(esperado.no_contiene, result.answer))
    if esperado.herramienta is not None:
        nombres = _tool_names(result)
        ok = esperado.herramienta in nombres
        detail = (
            f"se llamó a {esperado.herramienta!r}"
            if ok
            else f"no se llamó a {esperado.herramienta!r}; llamadas: {_fmt_names(nombres)}"
        )
        checks.append(CheckResult("herramienta", ok, detail))
    if esperado.max_pasos is not None:
        ok = result.steps <= esperado.max_pasos
        checks.append(CheckResult("max_pasos", ok, f"pasos: {result.steps} (máximo {esperado.max_pasos})"))
    if esperado.stop_reason is not None:
        ok = result.stop_reason == esperado.stop_reason
        checks.append(
            CheckResult("stop_reason", ok, f"terminó con {result.stop_reason!r} (esperado {esperado.stop_reason!r})")
        )
    return checks


def case_passed(checks: list[CheckResult]) -> bool:
    """True si hay comprobaciones y todas pasaron. Sin comprobaciones NO es acierto (nada se verificó)."""
    return bool(checks) and all(c.passed for c in checks)
