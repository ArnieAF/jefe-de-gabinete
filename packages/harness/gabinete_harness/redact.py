"""Limpieza de secretos en los textos que acaban en registros, reportes o pantalla (hallazgo de la auditoría de F1).

Un error HTTP de una librería suele traer la URL completa; si una clave viajó en la URL (`?key=...`), el texto del error la
filtra al registro JSONL, a los reportes de evals y a la salida que el usuario copia a un chat. `scrub()` sustituye por
`[REDACTADO]`:
- los valores de las variables de entorno cuyo nombre indica un secreto (`*_API_KEY`, `*_TOKEN`, `*_SECRET`, `*_PASSWORD`) y que
  midan al menos 8 caracteres (así una clave que viaje como "texto suelto" también se limpia);
- los parámetros de URL `key=`, `api_key=`, `token=`, `access_token=`, `auth=`, `password=` y `secret=`;
- formas de clave muy reconocibles: Gemini/Google (`AIza...`), `sk-...`, tokens de GitHub (`ghp_...`), de Slack (`xox...`) y
  `Bearer <token>`.

No sustituye a las buenas prácticas: los adaptadores deben enviar la clave en una cabecera (nunca en la URL) y no dejar escapar el
cuerpo ni la URL de los errores HTTP. Esto es la red de seguridad por si algo se les escapa.
"""
from __future__ import annotations

import os
import re

__all__ = ["REDACTED", "scrub"]

REDACTED = "[REDACTADO]"

_MIN_ENV_SECRET_CHARS = 8
_ENV_NAME_RE = re.compile(r"(?i)(?:^|_)(?:API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD)$")
_QUERY_RE = re.compile(
    r"(?i)([?&;](?:key|api[_-]?key|apikey|access[_-]?token|token|auth|password|secret)=)[^&\s\"'<>]+"
)
_KNOWN_RES = (
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/\-]{8,}=*"),
)


def _env_secrets() -> list[str]:
    """Valores de las variables de entorno que parecen secretos, de la más larga a la más corta."""
    valores = {
        valor
        for nombre, valor in os.environ.items()
        if _ENV_NAME_RE.search(nombre) and len(valor) >= _MIN_ENV_SECRET_CHARS
    }
    return sorted(valores, key=len, reverse=True)


def scrub(text: str) -> str:
    """Devuelve `text` con los secretos reconocibles sustituidos por `[REDACTADO]`. Un texto vacío vuelve igual."""
    if not text:
        return text
    limpio = text
    for secreto in _env_secrets():
        limpio = limpio.replace(secreto, REDACTED)
    limpio = _QUERY_RE.sub(lambda m: m.group(1) + REDACTED, limpio)
    for patron in _KNOWN_RES:
        limpio = patron.sub(REDACTED, limpio)
    return limpio
