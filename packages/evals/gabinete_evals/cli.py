"""Línea de comandos de los evals: `python -m gabinete_evals` (tarea T8).

Conecta `run()` (gabinete_harness.loop) con `ScriptedProvider`, el guardián de privacidad D10, el runner de T7 y los
reportes. Con el proveedor falso los casos comprueban el HARNESS (permisos, límites, registro), no a un modelo.

Orden del flujo (cada paso falla ANTES de tocar el siguiente):
  1. argumentos (argparse; errores de uso = 2)
  2. guardián D10 `check_data_policy`, antes que cualquier otra cosa: si lanza `DataPolicyError` no se ejecuta ningún
     caso ni se crea ninguna carpeta de salida (código 2)
  3. carga de casos (ValueError, suite vacía, caso sin guion o con guion mal formado = 2)
  4. ejecución de la suite (cada repetición parte de cero: bandeja de salida vacía, herramientas y proveedor nuevos)
  5. reportes JSON y Markdown y resumen en la salida estándar

Códigos de salida: 0 = la tasa total alcanza `--min-rate`; 1 = no la alcanza; 2 = error de uso o de configuración.

Seguridad: la CLI ejecuta TODO con `deny_all`: ninguna aprobación humana se concede nunca, de modo que `email.send` jamás
se ejecuta aquí (y de todos modos es simulada). No hay variable para saltarse el guardián D10. Ojo: `--repo-root` define
qué carpeta cuenta como `fixtures/` para el guardián; úsalo solo con repositorios propios (existe para las pruebas).
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO

from gabinete_evals.cases import Case, load_cases
from gabinete_evals.report import write_report
from gabinete_evals.suite import SuiteResult, run_suite
from gabinete_harness.eventlog import is_reserved_device_name
from gabinete_harness.loop import run
from gabinete_harness.policy import DataPolicyError, check_data_policy
from gabinete_harness.providers.scripted import ScriptedProvider
from gabinete_harness.tools.toy import make_calendar_tool, make_email_tool, make_notes_tool
from gabinete_harness.types import RunResult, Tool, deny_all

__all__ = ["DEFAULT_MAX_COST_USD", "DEFAULT_MAX_STEPS", "build_tools", "main", "make_execute", "session_id_for"]

EXIT_OK, EXIT_BELOW_MIN_RATE, EXIT_USAGE = 0, 1, 2
DEFAULT_MAX_STEPS = 8  # el de run(); un caso lo cambia con `limites.max_steps`
DEFAULT_MAX_COST_USD = 0.0  # 0.0 = sin límite; un caso lo cambia con `limites.max_cost_usd`
PROVIDERS = {"scripted": ScriptedProvider}  # los reales (ollama, gemini) llegan con T5
MAX_SESSION_ID_CHARS = 64  # el de run()
_SESSION_CHARS_RE = re.compile(r"[^A-Za-z0-9_.-]")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")  # el mismo formato que exige report.py (va en nombres de archivo)
_RUN_ID_TIME_FORMAT = "%Y%m%d-%H%M%S"  # ordena bien como texto: así "anterior" es el de menor run_id


# --- Piezas reutilizables (las usan también las pruebas) -----------------------------------------------------------
def session_id_for(case_id: str) -> str:
    """`"eval-"` + id del caso con lo que no sea [A-Za-z0-9_.-] cambiado por "-", recortado a 64 caracteres."""
    return ("eval-" + _SESSION_CHARS_RE.sub("-", case_id))[:MAX_SESSION_ID_CHARS]


def build_tools(repo_root: Path, notes_dir: Path, outbox: list) -> list[Tool]:
    """Las tres herramientas de juguete: calendario sobre `<repo>/fixtures/calendar.json`, notas sobre `notes_dir` y
    correo simulado sobre `outbox`. Se llama UNA VEZ por repetición, con una bandeja nueva."""
    return [
        make_calendar_tool(Path(repo_root) / "fixtures" / "calendar.json"),
        make_notes_tool(Path(notes_dir)),
        make_email_tool(outbox),
    ]


def make_execute(
    provider_name: str, repo_root: Path, notes_dir: Path, log_dir: Path
) -> Callable[[Case], RunResult]:
    """Arma el `execute(caso) -> RunResult` que recibe el runner. Cada llamada (cada repetición) parte de cero:
    bandeja de salida vacía, herramientas nuevas y un proveedor nuevo con el guion del caso. La aprobación es `deny_all`."""
    provider_cls = PROVIDERS[provider_name]

    def execute(caso: Case) -> RunResult:
        outbox: list = []
        tools = build_tools(repo_root, notes_dir, outbox)
        provider = provider_cls(copy.deepcopy(caso.guion))
        limites = caso.limites
        return run(
            caso.pregunta,
            session_id=session_id_for(caso.id),
            provider=provider,
            tools=tools,
            approve=deny_all,
            max_steps=limites.max_steps if limites is not None and limites.max_steps is not None else DEFAULT_MAX_STEPS,
            max_cost_usd=(
                limites.max_cost_usd if limites is not None and limites.max_cost_usd is not None else DEFAULT_MAX_COST_USD
            ),
            log_dir=log_dir,
        )

    return execute


# --- Salida --------------------------------------------------------------------------------------------------------
def _emit(text: str, stream: TextIO) -> None:
    """Imprime sin morir por una consola que no sabe codificar algún carácter (p. ej. cp1252 con emojis)."""
    try:
        print(text, file=stream)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        print(text.encode(encoding, "replace").decode(encoding), file=stream)


def _err(text: str) -> None:
    _emit(f"error: {text}", sys.stderr)


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f} %"


def _fmt_delta(delta: float) -> str:
    return "0.0 pp" if abs(delta) < 0.05 else f"{delta:+.1f} pp"


def render_summary(
    suite: SuiteResult,
    *,
    run_id: str,
    provider: str,
    min_rate: float,
    paths: tuple[Path, Path] | None = None,
    comparison: dict | None = None,
    warnings: list[str] | None = None,
) -> str:
    """Resumen legible: una línea por caso, los fallos, la tasa total, las rutas y el cambio frente a la corrida anterior."""
    ancho = max((len(o.case_id) for o in suite.outcomes), default=0)
    lines = [f"Evals del Jefe de Gabinete: corrida {run_id} (proveedor: {provider})", ""]
    for o in suite.outcomes:
        marca = "[OK]   " if o.passes == o.runs else "[FALLA]"
        lines.append(f"  {marca} {o.case_id.ljust(ancho)}  {o.passes}/{o.runs}  {_pct(o.rate).rjust(7)}")
        lines += [f"            - {texto}" for texto in o.failures]
    aprobado = suite.rate >= min_rate
    lines += [
        "",
        f"Tasa total: {suite.total_passes}/{suite.total_runs} ({_pct(suite.rate)}); "
        f"mínimo exigido: {_pct(min_rate)} -> {'APROBADO' if aprobado else 'NO APROBADO'}",
    ]
    if paths is not None:
        lines += [f"Reporte JSON: {paths[0]}", f"Reporte Markdown: {paths[1]}"]
    if comparison is not None and comparison.get("previous_run_id") is not None:
        lines.append(
            f"Cambio frente a la corrida anterior ({comparison['previous_run_id']}): {_fmt_delta(comparison['total_delta_pp'])}"
        )
        for cid, c in comparison.get("cases", {}).items():
            if c["status"] == "new":
                lines.append(f"  {cid}: caso nuevo")
            elif c["status"] == "removed":
                lines.append(f"  {cid}: ya no está en la suite (tasa anterior {_pct(c['previous_rate'])})")
            elif abs(c["delta_pp"]) >= 0.05:
                lines.append(f"  {cid}: {_fmt_delta(c['delta_pp'])}")
    else:
        lines.append("Sin corrida anterior con la que comparar.")
    lines += [f"Aviso: {aviso}" for aviso in warnings or []]
    return "\n".join(lines)


# --- Argumentos ----------------------------------------------------------------------------------------------------
def _ruta(texto: str) -> Path:
    if not texto.strip() or "\x00" in texto:
        raise argparse.ArgumentTypeError("la ruta no puede estar vacía")  # Path("") es "." y escribiría en el directorio actual
    return Path(texto)


def _tasa(texto: str) -> float:
    try:
        valor = float(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{texto!r} no es un número") from None
    if not math.isfinite(valor) or not 0.0 <= valor <= 1.0:
        raise argparse.ArgumentTypeError(f"debe estar entre 0 y 1, no {texto!r}")
    return valor


def _repeticiones(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{texto!r} no es un entero") from None
    if valor < 1:
        raise argparse.ArgumentTypeError(f"debe ser un entero >= 1, no {texto!r}")
    return valor


def _run_id(texto: str) -> str:
    if not _RUN_ID_RE.fullmatch(texto):
        raise argparse.ArgumentTypeError(
            f"{texto!r} no sirve: usa 1 a 64 caracteres entre letras, dígitos, '_', '.' y '-' (empezando por letra o dígito)"
        )
    if is_reserved_device_name(texto):
        raise argparse.ArgumentTypeError(f"{texto!r} es un nombre de dispositivo de Windows; usa otro")
    return texto


def _parser(repo_root_default: Path, cases_default: Path) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m gabinete_evals",
        description=(
            "Ejecuta los evals del Jefe de Gabinete y escribe un reporte JSON y otro Markdown. "
            "Códigos de salida: 0 = tasa total >= --min-rate, 1 = tasa menor, 2 = error de uso o de configuración."
        ),
    )
    p.add_argument("--cases", type=_ruta, default=cases_default, metavar="RUTA",
                   help="archivo .yaml o carpeta con casos (por defecto: packages/evals/cases)")
    p.add_argument("--out", type=_ruta, default=Path("evals-out"), metavar="CARPETA",
                   help="carpeta de salida: reportes y registros en <out>/runs/<run-id> (por defecto: evals-out)")
    p.add_argument("--min-rate", type=_tasa, default=1.0, metavar="TASA",
                   help="tasa total mínima, entre 0 y 1, para devolver 0 (por defecto: 1.0)")
    p.add_argument("--repetitions", type=_repeticiones, default=None, metavar="N",
                   help="repeticiones por caso (entero >= 1); si se da, manda sobre el valor de cada caso")
    p.add_argument("--run-id", type=_run_id, default=None, metavar="ID",
                   help="identificador de la corrida (por defecto: la hora local, AAAAMMDD-HHMMSS)")
    p.add_argument("--provider", choices=sorted(PROVIDERS), default="scripted",
                   help="proveedor del modelo (por ahora solo 'scripted', un guion fijo; los reales llegan con T5)")
    p.add_argument("--notes-dir", type=_ruta, default=None, metavar="CARPETA",
                   help="carpeta de notas que lee notes.read (por defecto: <repo>/fixtures/vault)")
    p.add_argument("--repo-root", type=_ruta, default=repo_root_default, metavar="CARPETA",
                   help="raíz del repositorio: de ahí salen fixtures/calendar.json y la carpeta fixtures/ del guardián D10")
    return p


def _parse(argv: list[str] | None, parser: argparse.ArgumentParser) -> argparse.Namespace | int:
    """Namespace, o el código de salida si argparse quiso salir (error de uso = 2, --help = 0). main() nunca llama a sys.exit."""
    try:
        return parser.parse_args(argv)
    except SystemExit as exc:  # argparse sale así tras imprimir el uso o la ayuda
        code = exc.code
        return code if isinstance(code, int) else EXIT_USAGE


# --- Programa ------------------------------------------------------------------------------------------------------
def _comprobar_casos(casos: list[Case]) -> list[str]:
    """Problemas de configuración que impiden ejecutar con el proveedor falso (lista vacía si todo está bien)."""
    problemas: list[str] = []
    sin_guion = [c.id for c in casos if not c.guion]
    if sin_guion:
        problemas.append("con el proveedor 'scripted' todo caso necesita 'guion'; faltan en: " + ", ".join(sin_guion))
    for c in casos:
        if c.guion:
            try:
                ScriptedProvider(copy.deepcopy(c.guion))  # solo valida el guion
            except ValueError as exc:
                problemas.append(f"caso {c.id!r}: guion inválido: {exc}")
    return problemas


def _comparacion(json_path: Path) -> tuple[dict | None, list[str]]:
    """(comparación, avisos) del reporte recién escrito; lo que se muestra es lo que quedó en disco."""
    try:
        reporte = json.loads(json_path.read_text(encoding="utf-8"))
        return reporte.get("comparison"), [str(a) for a in reporte.get("warnings", [])]
    except (OSError, ValueError, AttributeError):
        return None, ["no se pudo leer la comparación con la corrida anterior"]


def main(argv: list[str] | None = None) -> int:
    """Ejecuta los evals y devuelve el código de salida (0, 1 o 2). No llama a sys.exit."""
    repo_default = Path(__file__).resolve().parents[3]
    cases_default = Path(__file__).resolve().parents[1] / "cases"  # packages/evals/cases, junto al paquete
    parsed = _parse(argv, _parser(repo_default, cases_default))
    if isinstance(parsed, int):
        return parsed
    args = parsed
    repo_root: Path = args.repo_root
    notes_dir: Path = args.notes_dir if args.notes_dir is not None else repo_root / "fixtures" / "vault"
    run_id: str = args.run_id if args.run_id is not None else datetime.now().strftime(_RUN_ID_TIME_FORMAT)
    out: Path = args.out

    # 2. Guardián D10: ANTES de cualquier otra cosa (sin cargar casos, sin crear carpetas). Se le pasa el nombre del
    #    proveedor que realmente se va a instanciar.
    try:
        check_data_policy(PROVIDERS[args.provider].name, notes_dir, repo_root)
    except DataPolicyError as exc:
        _emit(str(exc), sys.stderr)
        return EXIT_USAGE

    if not notes_dir.is_dir():
        _err("la carpeta de notas no existe o no es una carpeta (--notes-dir)")
        return EXIT_USAGE
    if not (repo_root / "fixtures" / "calendar.json").is_file():
        _err("no se encuentra fixtures/calendar.json dentro de --repo-root")
        return EXIT_USAGE

    # 3. Casos
    try:
        casos = load_cases(args.cases)
    except ValueError as exc:
        _err(str(exc))
        return EXIT_USAGE
    if not casos:
        _err("no hay casos que ejecutar: una suite vacía no cuenta como aprobada")
        return EXIT_USAGE
    problemas = _comprobar_casos(casos)
    if problemas:
        for problema in problemas:
            _err(problema)
        return EXIT_USAGE

    # El run_id repetido se detecta antes de ejecutar nada (write_report también lo rechaza, pero tarde).
    if any((out / f"report-{run_id}{ext}").exists() for ext in (".json", ".md")):
        _err(f"ya existe un reporte con run_id {run_id!r} en la carpeta de salida; usa otro --run-id")
        return EXIT_USAGE

    # 4. Ejecución
    execute = make_execute(args.provider, repo_root, notes_dir, out / "runs" / run_id)
    suite = run_suite(casos, execute, repetitions=args.repetitions)

    # 5. Reportes y resumen
    try:
        json_path, md_path = write_report(suite, out, run_id)
    except FileExistsError:
        _err(f"ya existe un reporte con run_id {run_id!r} en la carpeta de salida; usa otro --run-id")
        return EXIT_USAGE
    except OSError as exc:
        _err(f"no se pudo escribir el reporte ({type(exc).__name__})")
        return EXIT_USAGE
    comparison, warnings = _comparacion(json_path)
    _emit(
        render_summary(
            suite,
            run_id=run_id,
            provider=args.provider,
            min_rate=args.min_rate,
            paths=(json_path, md_path),
            comparison=comparison,
            warnings=warnings,
        ),
        sys.stdout,
    )
    return EXIT_OK if suite.rate >= args.min_rate else EXIT_BELOW_MIN_RATE
