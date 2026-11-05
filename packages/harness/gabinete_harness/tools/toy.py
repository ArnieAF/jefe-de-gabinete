"""Herramientas de juguete del harness (tarea T3): calendario, notas y correo simulado.

Trabajan solo sobre `fixtures/` (datos falsos). Todas las funciones reciben un dict `arguments`, devuelven un
texto JSON y NUNCA lanzan por entradas inválidas: los errores se devuelven como `{"error": "..."}`. Los mensajes de
error no incluyen rutas absolutas del equipo.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from gabinete_harness.types import Tool, ToolSpec

# --- Límites ---------------------------------------------------------------------------------------------------
MAX_NOTE_CHARS = 100_000  # caracteres de una nota que se devuelven al modelo
MAX_PATH_CHARS = 1_000
MAX_EMAIL_TO_CHARS = 320
MAX_EMAIL_SUBJECT_CHARS = 998
MAX_EMAIL_BODY_CHARS = 100_000

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")  # solo dígitos ASCII; `fullmatch` no admite salto de línea final
_DRIVE_RE = re.compile(r"[A-Za-z]:")
_SEPARATORS_RE = re.compile(r"[\\/]+")
# Nombres de dispositivo de Windows: abrirlos puede bloquear o saltarse la carpeta, se rechazan en cualquier sistema.
_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _error(message: str) -> str:
    return _json({"error": message})


def _short(value: object, limit: int = 40) -> str:
    """Representación corta de un dato no confiable para incluirlo en un mensaje de error."""
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _check_arguments(arguments: object, allowed: tuple[str, ...]) -> str | None:
    """Comprueba que `arguments` sea un dict con exactamente las claves `allowed`. Devuelve el error o `None`."""
    if not isinstance(arguments, dict):
        return "los argumentos deben ser un objeto JSON"
    missing = [key for key in allowed if key not in arguments]
    if missing:
        return "falta(n) argumento(s) obligatorio(s): " + ", ".join(missing)
    extra = [key for key in arguments if key not in allowed]
    if extra:
        return "argumento(s) no permitido(s): " + ", ".join(_short(key) for key in extra[:5])
    return None


def _schema(properties: dict[str, dict]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# --- calendar.list_events --------------------------------------------------------------------------------------
def _instant(moment: datetime) -> datetime:
    """Instante comparable: con desfase horario pasa a UTC; sin él se toma como UTC (solo para ordenar)."""
    if moment.utcoffset() is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def make_calendar_tool(calendar_path: Path) -> Tool:
    """`calendar.list_events(date)`: solo lectura. Lee `calendar_path` (JSON) en cada llamada."""
    calendar_path = Path(calendar_path)

    def list_events(arguments: dict) -> str:
        problem = _check_arguments(arguments, ("date",))
        if problem:
            return _error(problem)
        raw_date = arguments["date"]
        if not isinstance(raw_date, str) or not _DATE_RE.fullmatch(raw_date):
            return _error("'date' debe ser un texto con formato YYYY-MM-DD")
        try:
            day = date.fromisoformat(raw_date)
        except ValueError:
            return _error("'date' no es una fecha real del calendario")

        try:
            events = json.loads(calendar_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # UnicodeDecodeError y JSONDecodeError son ValueError
            return _error("el calendario no está disponible o no tiene un formato válido")
        if not isinstance(events, list):
            return _error("el calendario no tiene un formato válido")

        found: list[tuple[datetime, dict]] = []
        for event in events:
            if not isinstance(event, dict) or not isinstance(event.get("inicio"), str):
                continue  # un evento mal formado no tumba la consulta: se ignora
            try:
                start = datetime.fromisoformat(event["inicio"])
            except ValueError:
                continue
            if start.date() == day:  # fecha local: la de su propio desfase horario
                found.append((start, event))
        found.sort(key=lambda pair: _instant(pair[0]))  # estable: empates conservan el orden del archivo
        return _json([event for _, event in found])

    spec = ToolSpec(
        name="calendar.list_events",
        description=(
            "Lista los eventos del calendario de un día (solo lectura). Devuelve un JSON con la lista de eventos "
            "(id, titulo, inicio, fin, asistentes, lugar) ordenados por hora de inicio; '[]' si no hay ninguno."
        ),
        schema=_schema(
            {"date": {"type": "string", "description": "Fecha local del evento en formato YYYY-MM-DD, por ejemplo 2026-11-05."}}
        ),
    )
    return Tool(spec=spec, fn=list_events, requires_approval=False)


# --- notes.read ------------------------------------------------------------------------------------------------
class _InvalidPath(Exception):
    """Ruta rechazada; el mensaje es seguro de mostrar al modelo (sin rutas del equipo)."""


def _parse_note_path(raw: object) -> list[str]:
    """Valida el texto de la ruta y devuelve sus componentes relativos. Lanza `_InvalidPath` si no es aceptable."""
    if not isinstance(raw, str):
        raise _InvalidPath("'path' debe ser un texto")
    if len(raw) > MAX_PATH_CHARS:
        raise _InvalidPath("'path' es demasiado largo")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise _InvalidPath("'path' contiene caracteres de control")
    text = raw.strip()
    if not text:
        raise _InvalidPath("'path' está vacío")
    if text[0] in "/\\" or _DRIVE_RE.match(text):
        raise _InvalidPath("no se permiten rutas absolutas: usa una ruta relativa a la carpeta de notas")
    if ":" in text:
        raise _InvalidPath("el carácter ':' no está permitido en la ruta")

    parts: list[str] = []
    for part in _SEPARATORS_RE.split(text):
        if part in ("", "."):
            continue
        if part.rstrip(" .") == "":  # "..", "...", ".. ": Windows los normaliza a ".." o a la carpeta actual
            raise _InvalidPath("no se permite '..' en la ruta")
        if part.split(".")[0].rstrip(" ").upper() in _RESERVED_NAMES:
            raise _InvalidPath("nombre de archivo no permitido")
        parts.append(part)
    if not parts:
        raise _InvalidPath("'path' debe indicar un archivo dentro de la carpeta de notas")
    return parts


def make_notes_tool(vault_dir: Path) -> Tool:
    """`notes.read(path)`: solo lectura de un archivo dentro de `vault_dir`; rechaza cualquier intento de salir."""
    vault_dir = Path(vault_dir)

    def read(arguments: dict) -> str:
        problem = _check_arguments(arguments, ("path",))
        if problem:
            return _error(problem)
        try:
            parts = _parse_note_path(arguments["path"])
        except _InvalidPath as exc:
            return _error(str(exc))

        # Defensa principal: resolver (con enlaces simbólicos) y comprobar que el destino queda dentro del vault.
        try:
            root = vault_dir.resolve()
            target = root.joinpath(*parts).resolve()
        except (OSError, RuntimeError, ValueError):
            return _error("no se pudo resolver la ruta")
        if not target.is_relative_to(root):
            return _error("la ruta queda fuera de la carpeta de notas")
        if not target.exists():
            return _error("la nota no existe")
        if not target.is_file():
            return _error("la ruta no es un archivo")

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read(MAX_NOTE_CHARS + 1)
        except OSError:
            return _error("no se pudo leer la nota")

        truncated = len(content) > MAX_NOTE_CHARS
        if truncated:
            content = content[:MAX_NOTE_CHARS] + f"\n[... contenido truncado a {MAX_NOTE_CHARS} caracteres ...]"
        result: dict[str, object] = {"path": "/".join(parts), "content": content}
        if truncated:
            result["truncado"] = True
        return _json(result)

    spec = ToolSpec(
        name="notes.read",
        description=(
            "Lee una nota de la carpeta de notas (solo lectura). 'path' es una ruta RELATIVA a esa carpeta, por "
            "ejemplo 'perfil.md' o 'proyectos/tienda-andina.md'. No admite rutas absolutas ni '..'. Devuelve un JSON "
            "con 'path' y 'content' (truncado a 100000 caracteres)."
        ),
        schema=_schema(
            {"path": {"type": "string", "description": "Ruta relativa a la carpeta de notas, con '/' como separador."}}
        ),
    )
    return Tool(spec=spec, fn=read, requires_approval=False)


# --- email.send (simulada) -------------------------------------------------------------------------------------
def make_email_tool(outbox: list) -> Tool:
    """`email.send(to, subject, body)`: SIMULADA. No envía nada ni usa la red: agrega el correo a `outbox`."""
    if not isinstance(outbox, list):
        raise TypeError("outbox debe ser una lista")

    def send(arguments: dict) -> str:
        problem = _check_arguments(arguments, ("to", "subject", "body"))
        if problem:
            return _error(problem)
        to, subject, body = arguments["to"], arguments["subject"], arguments["body"]
        for label, value in (("to", to), ("subject", subject), ("body", body)):
            if not isinstance(value, str):
                return _error(f"'{label}' debe ser un texto")
        if not to.strip():
            return _error("'to' no puede estar vacío")
        if any(char in to or char in subject for char in "\r\n"):
            return _error("'to' y 'subject' no pueden contener saltos de línea")
        if len(to) > MAX_EMAIL_TO_CHARS:
            return _error(f"'to' supera {MAX_EMAIL_TO_CHARS} caracteres")
        if len(subject) > MAX_EMAIL_SUBJECT_CHARS:
            return _error(f"'subject' supera {MAX_EMAIL_SUBJECT_CHARS} caracteres")
        if len(body) > MAX_EMAIL_BODY_CHARS:
            return _error(f"'body' supera {MAX_EMAIL_BODY_CHARS} caracteres")
        outbox.append({"to": to, "subject": subject, "body": body})
        return _json({"status": "enviado (simulado)"})

    spec = ToolSpec(
        name="email.send",
        description=(
            "Envía un correo electrónico. Requiere aprobación humana. En este entorno es SIMULADA: no se envía "
            "nada real, el correo solo queda en una bandeja de salida en memoria."
        ),
        schema=_schema(
            {
                "to": {"type": "string", "description": "Dirección del destinatario."},
                "subject": {"type": "string", "description": "Asunto del correo, en una sola línea."},
                "body": {"type": "string", "description": "Cuerpo del correo en texto plano."},
            }
        ),
    )
    return Tool(spec=spec, fn=send, requires_approval=True)


# --- Conjunto por defecto --------------------------------------------------------------------------------------
def default_toy_tools(repo_root: Path, outbox: list | None = None) -> list[Tool]:
    """Las tres herramientas sobre `repo_root/fixtures`. Si no se pasa `outbox` se crea una lista propia."""
    repo_root = Path(repo_root)
    if outbox is None:  # `is None`, no `or []`: una lista vacía del llamador debe conservarse
        outbox = []
    return [
        make_calendar_tool(repo_root / "fixtures" / "calendar.json"),
        make_notes_tool(repo_root / "fixtures" / "vault"),
        make_email_tool(outbox),
    ]
