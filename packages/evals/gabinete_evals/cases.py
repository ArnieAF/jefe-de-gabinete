"""Casos de eval: formato YAML, dataclasses y carga con validación estricta (tarea T7).

El YAML es una LISTA de casos (formato en docs/F1-tareas.md). Toda errata (clave desconocida, clave
repetida, tipo equivocado) falla con un `ValueError` que indica el archivo y el id del caso, para que
un caso mal escrito no se califique en silencio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from gabinete_harness.types import STOP_REASONS

# Claves permitidas. `sesiones` es del formato de PLAN sección 5 (casos de memoria, F4): se conserva en `raw`.
CASE_KEYS = ("id", "capa", "pregunta", "guion", "esperado", "repeticiones", "sesiones")
EXPECT_KEYS = ("contiene", "no_contiene", "herramienta", "max_pasos", "stop_reason")
DEFAULT_CAPA = "sin-capa"


@dataclass
class Expect:
    """Criterios que se califican por código. Lista vacía / None = criterio no pedido."""

    contiene: list[str] = field(default_factory=list)
    no_contiene: list[str] = field(default_factory=list)
    herramienta: str | None = None
    max_pasos: int | None = None
    stop_reason: str | None = None

    def has_criteria(self) -> bool:
        """True si hay al menos un criterio que calificar."""
        return bool(
            self.contiene
            or self.no_contiene
            or self.herramienta is not None
            or self.max_pasos is not None
            or self.stop_reason is not None
        )


@dataclass
class Case:
    """Un caso de eval. `raw` conserva el diccionario original del YAML."""

    id: str
    capa: str
    pregunta: str
    esperado: Expect
    repeticiones: int = 1
    guion: list | None = None
    raw: dict = field(default_factory=dict)


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader que rechaza claves repetidas en un mismo mapa (PyYAML se queda con la última sin avisar)."""


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    seen: set = set()
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            continue
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"clave repetida {key!r}", key_node.start_mark
                )
            seen.add(key)
        except TypeError:  # clave no hashable: que la rechace SafeLoader con su mensaje normal
            pass
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _fail(origin: str, case_id: str | None, message: str) -> ValueError:
    quien = f"caso {case_id!r}" if case_id else "caso"
    return ValueError(f"{origin}: {quien}: {message}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)  # bool es subclase de int


def _phrases(value: Any, clave: str, origin: str, case_id: str) -> list[str]:
    """Normaliza `contiene` / `no_contiene`: None -> [], texto -> [texto], lista -> lista de textos no vacíos."""
    if value is None:
        return []
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list):
        raise _fail(origin, case_id, f"'{clave}' debe ser un texto o una lista de textos")
    for item in items:
        if not isinstance(item, str):
            raise _fail(
                origin,
                case_id,
                f"'{clave}' solo admite textos y se encontró {item!r} "
                "(en YAML, valores como no/yes/2026 deben ir entre comillas)",
            )
        if not item.strip():
            raise _fail(origin, case_id, f"'{clave}' tiene una frase vacía (siempre coincidiría)")
    return list(items)


def _parse_expect(raw: Any, origin: str, case_id: str) -> Expect:
    if not isinstance(raw, dict):
        raise _fail(origin, case_id, "'esperado' debe ser un mapa con los criterios")
    unknown = sorted(str(k) for k in raw if k not in EXPECT_KEYS)
    if unknown:
        raise _fail(
            origin, case_id, f"claves desconocidas en 'esperado': {', '.join(unknown)} (permitidas: {', '.join(EXPECT_KEYS)})"
        )
    herramienta = raw.get("herramienta")
    if herramienta is not None and (not isinstance(herramienta, str) or not herramienta.strip()):
        raise _fail(origin, case_id, "'herramienta' debe ser un texto no vacío")
    max_pasos = raw.get("max_pasos")
    if max_pasos is not None and (not _is_int(max_pasos) or max_pasos < 1):
        raise _fail(origin, case_id, f"'max_pasos' debe ser un entero positivo, no {max_pasos!r}")
    stop_reason = raw.get("stop_reason")
    if stop_reason is not None and stop_reason not in STOP_REASONS:
        raise _fail(origin, case_id, f"'stop_reason' {stop_reason!r} inválido; los permitidos son {STOP_REASONS}")
    expect = Expect(
        contiene=_phrases(raw.get("contiene"), "contiene", origin, case_id),
        no_contiene=_phrases(raw.get("no_contiene"), "no_contiene", origin, case_id),
        herramienta=herramienta,
        max_pasos=max_pasos,
        stop_reason=stop_reason,
    )
    if not expect.has_criteria():
        raise _fail(origin, case_id, "'esperado' no tiene ningún criterio; un caso sin criterios pasaría siempre")
    return expect


def _parse_case(raw: Any, origin: str, position: int) -> Case:
    if not isinstance(raw, dict):
        raise ValueError(f"{origin}: el elemento #{position} debe ser un mapa (caso), no {type(raw).__name__}")
    case_id = raw.get("id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError(f"{origin}: el caso #{position} no tiene 'id' (debe ser un texto no vacío)")
    unknown = sorted(str(k) for k in raw if k not in CASE_KEYS)
    if unknown:
        raise _fail(origin, case_id, f"claves desconocidas: {', '.join(unknown)} (permitidas: {', '.join(CASE_KEYS)})")
    pregunta = raw.get("pregunta")
    if not isinstance(pregunta, str) or not pregunta.strip():
        raise _fail(origin, case_id, "falta 'pregunta' (debe ser un texto no vacío)")
    capa = raw.get("capa", DEFAULT_CAPA)
    if not isinstance(capa, str) or not capa.strip():
        raise _fail(origin, case_id, "'capa' debe ser un texto no vacío")
    repeticiones = raw.get("repeticiones", 1)
    if not _is_int(repeticiones) or repeticiones < 1:
        raise _fail(origin, case_id, f"'repeticiones' debe ser un entero >= 1, no {repeticiones!r}")
    guion = raw.get("guion")
    if guion is not None and not isinstance(guion, list):
        raise _fail(origin, case_id, "'guion' debe ser una lista de respuestas")
    esperado = _parse_expect(raw.get("esperado"), origin, case_id)
    return Case(
        id=case_id,
        capa=capa,
        pregunta=pregunta,
        esperado=esperado,
        repeticiones=repeticiones,
        guion=guion,
        raw=dict(raw),
    )


def _load_file(path: Path) -> list[Case]:
    origin = str(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{origin}: no se pudo leer ({type(exc).__name__})") from exc
    try:
        data = yaml.load(text, Loader=_StrictLoader)  # noqa: S506 - _StrictLoader hereda de SafeLoader
    except yaml.YAMLError as exc:
        raise ValueError(f"{origin}: YAML inválido: {exc}") from exc
    if data is None:
        raise ValueError(f"{origin}: el archivo está vacío; se esperaba una lista de casos")
    if not isinstance(data, list):
        raise ValueError(f"{origin}: la raíz debe ser una LISTA de casos, no {type(data).__name__}")
    return [_parse_case(item, origin, i) for i, item in enumerate(data, start=1)]


def load_cases(path: str | Path) -> list[Case]:
    """Carga casos de un archivo .yaml o de todos los *.yaml de una carpeta (orden alfabético).

    Lanza `ValueError` (con archivo e id) ante cualquier problema: ruta inexistente, YAML inválido,
    caso mal formado o ids repetidos, también entre archivos.
    """
    p = Path(path)
    if p.is_dir():
        files = sorted((f for f in p.glob("*.yaml") if f.is_file()), key=lambda f: (f.name.casefold(), f.name))
        if not files:
            raise ValueError(f"{p}: la carpeta no contiene archivos *.yaml")
    elif p.is_file():
        files = [p]
    else:
        raise ValueError(f"{p}: no existe (se esperaba un archivo .yaml o una carpeta)")
    cases: list[Case] = []
    origins: dict[str, str] = {}
    for file in files:
        for case in _load_file(file):
            if case.id in origins:
                raise ValueError(f"{file}: caso {case.id!r}: id repetido (ya definido en {origins[case.id]})")
            origins[case.id] = str(file)
            cases.append(case)
    return cases
