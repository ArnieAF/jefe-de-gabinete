"""Registro de eventos de una corrida del agente (tarea T4): un archivo JSONL por corrida.

Formato: `<log_dir>/<run_id>.jsonl`, UTF-8, UNA línea JSON por evento con las claves `run_id`, `type` y el payload. No hay
marcas de hora ni nada no determinista salvo el `run_id`, para que dos corridas iguales produzcan registros comparables.

Decisiones de diseño (es el rastro de auditoría de lo que el agente hizo, así que falla cerrado y no se deja engañar):
- Creación EXCLUSIVA (`O_EXCL`): si el archivo ya existe lanza `FileExistsError` (es un `OSError`); nunca se mezclan ni se
  pisan dos corridas, y tampoco se sigue un enlace simbólico que alguien haya dejado con ese nombre.
- Una línea = un evento, siempre. `json.dumps` escapa saltos de línea y caracteres de control, y aquí además se escapan
  U+2028, U+2029 y U+0085 (que `str.splitlines()` trata como saltos). Un texto del modelo o de una herramienta con
  "\\n{...}" no puede falsificar un evento: queda dentro de una cadena.
- Cada evento hace `flush`: si el proceso muere, lo escrito queda.
- Los textos largos se recortan a `MAX_TEXT_CHARS` (el marcador cuenta dentro del límite). El JSON siempre es válido:
  NaN e infinito pasan a texto, lo que no se puede serializar pasa por `repr`, y un sustituto Unicode suelto (un modelo
  puede producirlo) se escribe como `\\udXXX` en vez de hacer fallar la escritura.
- El archivo se crea con permisos 0o600 (y la carpeta nueva con 0o700) donde el sistema los respete: el registro puede
  contener texto de notas y correos. Con datos reales, `log_dir` debe apuntar FUERA del repo (`GABINETE_LOG_DIR`).
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

__all__ = [
    "DEFAULT_LOG_DIR",
    "LOG_DIR_ENV",
    "MAX_TEXT_CHARS",
    "TRUNCATION_MARKER",
    "EventLog",
    "is_reserved_device_name",
    "resolve_log_dir",
    "truncate_text",
]

LOG_DIR_ENV = "GABINETE_LOG_DIR"
DEFAULT_LOG_DIR = "evals-out"
MAX_TEXT_CHARS = 20_000
TRUNCATION_MARKER = "[... recortado ...]"

_RUN_ID_RE = re.compile(r"[A-Za-z0-9_.-]{1,100}")
_MAX_DEPTH = 12
_DEPTH_MARKER = "[... demasiado profundo ...]"
# Caracteres que `str.splitlines()` trata como salto de línea y que `json.dumps(ensure_ascii=False)` no escapa.
_LINE_BREAKERS = {0x2028: "\\u2028", 0x2029: "\\u2029", 0x85: "\\u0085"}
# Nombres de dispositivo de Windows: abrir `NUL.x` o `CON.x` escribe en el dispositivo y el registro se perdería en silencio.
_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)


def is_reserved_device_name(name: str) -> bool:
    """True si `name` (con o sin extensión) es un nombre de dispositivo de Windows como `NUL`, `CON` o `COM1`."""
    return name.split(".")[0].rstrip(" ").upper() in _RESERVED_NAMES


def truncate_text(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Devuelve `text` tal cual si cabe en `limit` caracteres; si no, lo recorta para que el resultado mida EXACTAMENTE
    `limit` (el marcador `TRUNCATION_MARKER` incluido)."""
    if len(text) <= limit:
        return text
    keep = max(limit - len(TRUNCATION_MARKER), 0)
    return (text[:keep] + TRUNCATION_MARKER)[:limit]


def resolve_log_dir(log_dir: str | os.PathLike | None = None) -> Path:
    """Carpeta de registros: la indicada; si no, la variable `GABINETE_LOG_DIR`; si tampoco, `evals-out` (relativa al
    directorio actual). Un texto vacío o en blanco (en el argumento o en la variable) cuenta como "no indicado".
    No toca el disco. Lanza `TypeError` si `log_dir` no es una ruta."""
    if log_dir is not None and not (isinstance(log_dir, str) and not log_dir.strip()):
        if isinstance(log_dir, bytes):
            raise TypeError("log_dir debe ser un texto o una ruta, no bytes")
        return Path(log_dir)
    from_env = os.environ.get(LOG_DIR_ENV, "")
    if from_env.strip():
        return Path(from_env)
    return Path(DEFAULT_LOG_DIR)


def _clean(value: Any, depth: int = 0) -> Any:
    """Convierte `value` en algo que `json.dumps` serialice sin error: recorta textos, evita NaN e infinitos y no se
    cae con objetos raros ni con estructuras circulares."""
    if isinstance(value, str):
        return truncate_text(value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if depth >= _MAX_DEPTH:
        return _DEPTH_MARKER
    if isinstance(value, dict):
        return {truncate_text(str(key)): _clean(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item, depth + 1) for item in value]
    try:
        return truncate_text(repr(value))
    except Exception:  # un __repr__ roto no debe tumbar el registro
        return f"<{type(value).__name__}>"


class EventLog:
    """Escribe los eventos de UNA corrida en `<log_dir>/<run_id>.jsonl`. Se usa como administrador de contexto.

    - Crea `log_dir` (con sus padres) si no existe. Lanza `OSError` si no puede crear la carpeta o el archivo (también
      `FileExistsError` si ese `run_id` ya tiene registro) y `ValueError` si el `run_id` no es un nombre seguro.
    - `emit(type, **payload)` escribe una línea y hace flush. Las claves `run_id` y `type` están reservadas.
    """

    def __init__(self, log_dir: str | os.PathLike, run_id: str) -> None:
        if not isinstance(run_id, str):
            raise TypeError(f"run_id debe ser un texto, no {type(run_id).__name__}")
        if not _RUN_ID_RE.fullmatch(run_id) or is_reserved_device_name(run_id):
            raise ValueError("run_id solo admite letras, dígitos, '_', '.' y '-' (1 a 100 caracteres) y no un nombre reservado")
        directory = Path(log_dir)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._run_id = run_id
        self._path = directory / f"{run_id}.jsonl"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(self._path, flags, 0o600)
        try:
            self._file = os.fdopen(fd, "w", encoding="utf-8", errors="backslashreplace", newline="\n")
        except BaseException:
            os.close(fd)
            raise
        self._closed = False

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def path(self) -> Path:
        return self._path

    def emit(self, type: str, /, **payload: Any) -> None:
        """Escribe un evento. `type` es el tipo (`run_start`, `tool_call`...) y `payload` sus datos."""
        if self._closed:
            raise ValueError("el registro ya está cerrado")
        if not isinstance(type, str) or not type:
            raise ValueError("el tipo de evento debe ser un texto no vacío")
        reserved = sorted({"run_id", "type"} & payload.keys())
        if reserved:
            raise ValueError(f"las claves {reserved} están reservadas y no pueden ir en el payload")
        record = {"run_id": self._run_id, "type": type, **{key: _clean(value) for key, value in payload.items()}}
        line = json.dumps(record, ensure_ascii=False, allow_nan=False).translate(_LINE_BREAKERS)
        self._file.write(line + "\n")  # una sola escritura: no queda una línea a medias salvo que el proceso muera en ella
        self._file.flush()

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._file.close()

    def __enter__(self) -> "EventLog":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
