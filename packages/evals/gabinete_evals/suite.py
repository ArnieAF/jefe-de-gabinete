"""Ejecución de una suite de casos con repeticiones (tarea T7).

El runner no conoce `run()` ni los proveedores: recibe `execute(caso) -> RunResult` ya armada por quien
lo llama (la CLI de T8). Así se prueba con funciones de juguete.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from gabinete_evals.cases import Case
from gabinete_evals.graders import case_passed, grade
from gabinete_harness.redact import scrub
from gabinete_harness.types import RunResult

ExecuteFn = Callable[[Case], RunResult]

_MAX_ERROR_CHARS = 300  # recorte del texto de una excepción (una sola línea, para JSON y Markdown)


@dataclass
class CaseOutcome:
    """Resultado agregado de un caso: `rate` = passes / runs, entre 0 y 1."""

    case_id: str
    capa: str
    runs: int
    passes: int
    rate: float
    failures: list[str] = field(default_factory=list)


@dataclass
class SuiteResult:
    """Resultado de toda la suite. Con 0 ejecuciones la tasa es 0.0 (no hay nada que afirmar)."""

    outcomes: list[CaseOutcome]
    total_runs: int
    total_passes: int
    rate: float


def _one_line(text: str, limit: int = _MAX_ERROR_CHARS) -> str:
    plano = " ".join(text.split())
    return plano if len(plano) <= limit else plano[:limit] + "…"


def _run_once(case: Case, execute: ExecuteFn) -> tuple[bool, list[str]]:
    """Ejecuta y califica una repetición. Devuelve (acierto, textos de comprobaciones fallidas)."""
    try:
        result = execute(case)
    except Exception as exc:  # noqa: BLE001 - una repetición rota cuenta como fallo y la suite sigue
        return False, [f"excepción: {type(exc).__name__}: {_one_line(scrub(str(exc)))}"]
    try:
        checks = grade(case, result)
    except Exception as exc:  # noqa: BLE001 - p. ej. execute devolvió algo que no es un RunResult
        return False, [f"error al calificar: {type(exc).__name__}: {_one_line(scrub(str(exc)))}"]
    if not checks:
        return False, ["sin criterios que calificar en 'esperado'"]
    return case_passed(checks), [f"{c.name}: {c.detail}" for c in checks if not c.passed]


def run_suite(cases: list[Case], execute: ExecuteFn, *, repetitions: int | None = None) -> SuiteResult:
    """Ejecuta cada caso `repeticiones` veces (o `repetitions` si se da: manda sobre todos los casos).

    Orden determinista: el de `cases`, y las repeticiones una tras otra. Si `execute` lanza una excepción,
    esa repetición cuenta como fallo y la suite continúa (KeyboardInterrupt sí la detiene).
    """
    if repetitions is not None and (isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1):
        raise ValueError(f"repetitions debe ser un entero >= 1, no {repetitions!r}")
    ids = [c.id for c in cases]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise ValueError(f"ids de caso repetidos: {', '.join(repetidos)}")

    outcomes: list[CaseOutcome] = []
    for case in cases:
        veces = repetitions if repetitions is not None else case.repeticiones
        if isinstance(veces, bool) or not isinstance(veces, int) or veces < 1:
            raise ValueError(f"caso {case.id!r}: 'repeticiones' debe ser un entero >= 1, no {veces!r}")
        passes = 0
        failures: list[str] = []
        for _ in range(veces):
            ok, fallos = _run_once(case, execute)
            passes += ok
            for texto in fallos:
                if texto not in failures:  # sin duplicar el mismo texto
                    failures.append(texto)
        outcomes.append(
            CaseOutcome(case_id=case.id, capa=case.capa, runs=veces, passes=passes, rate=passes / veces, failures=failures)
        )
    total_runs = sum(o.runs for o in outcomes)
    total_passes = sum(o.passes for o in outcomes)
    return SuiteResult(
        outcomes=outcomes,
        total_runs=total_runs,
        total_passes=total_passes,
        rate=total_passes / total_runs if total_runs else 0.0,
    )
