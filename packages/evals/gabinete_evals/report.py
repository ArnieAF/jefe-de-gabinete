"""Reportes de evals: JSON + Markdown comparables entre corridas (tarea T7).

Los archivos se llaman `report-<run_id>.json` y `report-<run_id>.md`. El `run_id` lo da quien llama
(la CLI); aquí no se lee ningún reloj, así que los reportes no llevan marcas de hora y salen
idénticos para los mismos resultados. Los `run_id` se ordenan como TEXTO: usa un formato que ordene
bien (p. ej. `20261105-153000`).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from gabinete_evals.suite import SuiteResult

REPORT_FORMAT = 1
_PREFIX, _SUFFIX = "report-", ".json"
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")  # va dentro del nombre de archivo: sin rutas ni ":"
_MAX_REPORT_BYTES = 5_000_000  # un JSON más grande que esto no es un reporte nuestro


def _check_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError(
            f"run_id inválido {run_id!r}: usa 1 a 64 caracteres entre letras, dígitos, '_', '.' y '-' "
            "(empezando por letra o dígito)"
        )


def _pp(rate_now: float, rate_before: float) -> float:
    """Diferencia en puntos porcentuales, redondeada (sin ruido de coma flotante ni -0.0)."""
    return round((rate_now - rate_before) * 100, 2) + 0.0


def build_report(suite: SuiteResult, run_id: str) -> dict:
    """Diccionario del reporte (lo que se guarda en el JSON, sin la comparación)."""
    _check_run_id(run_id)
    return {
        "format": REPORT_FORMAT,
        "run_id": run_id,
        "total_runs": suite.total_runs,
        "total_passes": suite.total_passes,
        "rate": suite.rate,
        "outcomes": [asdict(o) for o in suite.outcomes],
    }


def compare(current: dict, previous: dict | None) -> dict:
    """Diferencia de tasas frente al reporte anterior, en puntos porcentuales.

    Devuelve `{"previous_run_id", "total_delta_pp", "cases"}`. `cases` va por id con `status`:
    `compared` (con `delta_pp`), `new` (solo en el actual) o `removed` (solo en el anterior).
    Sin reporte anterior: `previous_run_id` y `total_delta_pp` son None y `cases` está vacío.
    """
    if previous is None:
        return {"previous_run_id": None, "total_delta_pp": None, "cases": {}}
    before = {o["case_id"]: o for o in previous.get("outcomes", [])}
    cases: dict[str, dict] = {}
    for outcome in current.get("outcomes", []):
        cid = outcome["case_id"]
        if cid in before:
            cases[cid] = {
                "status": "compared",
                "rate": outcome["rate"],
                "previous_rate": before[cid]["rate"],
                "delta_pp": _pp(outcome["rate"], before[cid]["rate"]),
            }
        else:
            cases[cid] = {"status": "new", "rate": outcome["rate"], "previous_rate": None, "delta_pp": None}
    now = {o["case_id"] for o in current.get("outcomes", [])}
    for cid, outcome in before.items():
        if cid not in now:
            cases[cid] = {"status": "removed", "rate": None, "previous_rate": outcome["rate"], "delta_pp": None}
    return {
        "previous_run_id": previous.get("run_id") or "desconocido",
        "total_delta_pp": _pp(current["rate"], previous["rate"]),
        "cases": cases,
    }


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _report_problem(data: object, run_id: str) -> str | None:
    """None si `data` tiene la forma de un reporte nuestro; si no, el motivo (sin detalles internos)."""
    if not isinstance(data, dict):
        return "no es un reporte (la raíz no es un objeto)"
    if data.get("run_id") != run_id:
        return "su run_id interno no coincide con el nombre del archivo"
    if not _is_number(data.get("rate")) or not isinstance(data.get("outcomes"), list):
        return "le faltan campos del reporte ('rate' u 'outcomes')"
    for o in data["outcomes"]:
        if not isinstance(o, dict) or not isinstance(o.get("case_id"), str) or not _is_number(o.get("rate")):
            return "tiene un caso mal formado en 'outcomes'"
    return None


def _read_report(path: Path, run_id: str) -> tuple[dict | None, str | None]:
    """Lee un reporte JSON. Devuelve (reporte, None) o (None, motivo por el que se ignora)."""
    try:
        if path.stat().st_size > _MAX_REPORT_BYTES:
            return None, "es demasiado grande para ser un reporte"
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as exc:  # ValueError cubre JSON y UTF-8 inválidos
        return None, f"ilegible ({type(exc).__name__})"
    problem = _report_problem(data, run_id)
    return (None, problem) if problem else (data, None)


def find_previous(out_dir: str | Path, current_run_id: str) -> tuple[dict | None, list[str]]:
    """Reporte anterior de `out_dir` y avisos de los archivos que se ignoraron.

    Anterior = el de mayor run_id (como texto) que sea menor que `current_run_id`. Solo cuentan los
    archivos `report-<run_id>.json`; los ilegibles o mal formados se ignoran con un aviso y se prueba el
    siguiente más viejo. Una carpeta inexistente no es error: no hay anterior.
    """
    folder = Path(out_dir)
    avisos: list[str] = []
    if not folder.is_dir():
        return None, avisos
    candidatos: list[tuple[str, Path]] = []
    for f in folder.glob(f"{_PREFIX}*{_SUFFIX}"):
        if not (f.is_file() and f.name.startswith(_PREFIX) and f.name.endswith(_SUFFIX)):
            continue
        rid = f.name[len(_PREFIX) : -len(_SUFFIX)]
        if _RUN_ID_RE.fullmatch(rid) and rid < current_run_id:
            candidatos.append((rid, f))
    for rid, f in sorted(candidatos, reverse=True):
        report, problem = _read_report(f, rid)
        if problem:
            avisos.append(f"{f.name}: {problem}; se ignora")
            continue
        return report, avisos
    return None, avisos


def load_previous(out_dir: str | Path, current_run_id: str) -> dict | None:
    """Reporte JSON anterior (ver `find_previous`) o None. Si se ignoró algún archivo, va en `"avisos"`."""
    report, avisos = find_previous(out_dir, current_run_id)
    if report is not None and avisos:
        report["avisos"] = avisos
    return report


# --- Markdown ---------------------------------------------------------------------------------------


def _cell(text: object) -> str:
    """Texto seguro para una celda de tabla o un ítem: una sola línea y sin '|' sueltos."""
    return " ".join(str(text).split()).replace("|", "\\|")


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f} %"


def _fmt_delta(delta: float) -> str:
    return "0.0 pp" if abs(delta) < 0.05 else f"{delta:+.1f} pp"


def _change_cell(cmp_case: dict | None, has_previous: bool) -> str:
    if not has_previous or cmp_case is None:
        return "-"
    return "nuevo" if cmp_case["status"] == "new" else _fmt_delta(cmp_case["delta_pp"])


def render_markdown(report: dict) -> str:
    """Markdown del reporte (sin marcas de hora). `report` es el diccionario de `write_report`."""
    comparison = report.get("comparison") or {"previous_run_id": None, "total_delta_pp": None, "cases": {}}
    has_previous = comparison["previous_run_id"] is not None
    lines = [
        f"# Reporte de evals: {_cell(report['run_id'])}",
        "",
        f"**Tasa total: {_pct(report['rate'])}** ({report['total_passes']}/{report['total_runs']} ejecuciones)",
        "",
    ]
    if has_previous:
        lines.append(
            f"Cambio frente al reporte anterior ({_cell(comparison['previous_run_id'])}): "
            f"{_fmt_delta(comparison['total_delta_pp'])}"
        )
    else:
        lines.append("Sin reporte anterior con el que comparar.")
    lines += ["", "| Caso | Capa | Aciertos | Tasa | Cambio |", "|---|---|---|---|---|"]
    for o in report["outcomes"]:
        cambio = _change_cell(comparison["cases"].get(o["case_id"]), has_previous)
        lines.append(
            f"| {_cell(o['case_id'])} | {_cell(o['capa'])} | {o['passes']}/{o['runs']} | {_pct(o['rate'])} | {cambio} |"
        )
    removed = [(cid, c) for cid, c in comparison["cases"].items() if c["status"] == "removed"]
    if removed:
        lines += ["", "## Casos que estaban en el reporte anterior y ya no están", ""]
        lines += [f"- {_cell(cid)} (tasa anterior {_pct(c['previous_rate'])})" for cid, c in removed]
    with_failures = [o for o in report["outcomes"] if o["failures"]]
    if with_failures:
        lines += ["", "## Fallos", ""]
        for o in with_failures:
            lines.append(f"- **{_cell(o['case_id'])}**")
            lines += [f"  - {_cell(texto)}" for texto in o["failures"]]
    if report.get("warnings"):
        lines += ["", "## Avisos", ""]
        lines += [f"- {_cell(a)}" for a in report["warnings"]]
    return "\n".join(lines) + "\n"


def write_report(
    suite: SuiteResult, out_dir: str | Path, run_id: str, *, overwrite: bool = False
) -> tuple[Path, Path]:
    """Escribe `report-<run_id>.json` y `.md` en `out_dir` (se crea si no existe) y devuelve sus rutas.

    Compara con el reporte anterior de esa carpeta (`find_previous`). No pisa un reporte con el mismo
    run_id salvo `overwrite=True`: perder la línea base en silencio falsearía las comparaciones.
    Lanza `ValueError` si el run_id no sirve como parte de un nombre de archivo y `FileExistsError` si ya existe.
    """
    report = build_report(suite, run_id)  # valida run_id antes de tocar el disco
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / f"{_PREFIX}{run_id}{_SUFFIX}"
    md_path = folder / f"{_PREFIX}{run_id}.md"
    if not overwrite:
        for path in (json_path, md_path):
            if path.exists():
                raise FileExistsError(f"{path} ya existe; usa otro run_id u overwrite=True")
    previous, avisos = find_previous(folder, run_id)
    report["comparison"] = compare(report, previous)
    report["warnings"] = avisos
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    md_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return json_path, md_path
