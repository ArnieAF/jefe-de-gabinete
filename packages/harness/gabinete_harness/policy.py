"""Guardián de privacidad D10: los datos reales solo pasan por modelos locales.

Regla (PLAN.md, decisión D10): solo el proveedor `ollama` (modelo local) puede leer notas de cualquier carpeta. Cualquier
otro proveedor (gemini, anthropic, scripted, desconocido, cadena vacía...) se trata como NUBE y solo puede leer dentro
de `<raíz del repo>/fixtures` (datos falsos).

Decisiones de diseño:
- No hay parámetro ni variable de entorno para saltarse la regla. Si hace falta cambiarla, se cambia el código y se revisa.
- Falla cerrado: ante cualquier duda (ruta vacía, tipo raro, byte nulo, error del sistema de archivos) lanza `DataPolicyError`.
- Los mensajes de error indican el motivo y el proveedor, pero nunca la ruta (puede contener el nombre de usuario).
- La carpeta de notas se resuelve (`..` y enlaces simbólicos o uniones) antes de compararla por componentes de ruta, no por
  prefijo de texto: `fixtures-real` no pasa como `fixtures`. En Windows la comparación ignora mayúsculas.
- Se resuelve la raíz del repo, pero NO la carpeta `fixtures` en sí: si `fixtures` fuera un enlace hacia otro lado, nada
  pasaría por ella (falla cerrado) en vez de abrirle la puerta a los datos reales.
- Límites conocidos: es una comprobación puntual (un enlace cambiado después no se detecta; las herramientas de lectura
  deben confinarse por su cuenta) y una ruta relativa se interpreta desde el directorio de trabajo actual.
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = ["DataPolicyError", "check_data_policy"]

PROVEEDOR_LOCAL = "ollama"
CARPETA_NUBE = "fixtures"
_MAX_ETIQUETA = 40  # largo máximo del nombre del proveedor dentro de un mensaje de error


class DataPolicyError(Exception):
    """La política D10 impide leer esa carpeta de notas con ese proveedor."""


def _etiqueta(proveedor: str) -> str:
    """Nombre del proveedor listo para un mensaje: acotado y con `repr` para que no cuele saltos de línea."""
    texto = repr(proveedor[:_MAX_ETIQUETA])
    return texto if len(proveedor) <= _MAX_ETIQUETA else texto + "..."


def _normalizar_proveedor(nombre: object) -> str:
    """strip y minúsculas; todo lo que no sea texto queda como cadena vacía (y por tanto como nube)."""
    return nombre.strip().lower() if isinstance(nombre, str) else ""


def _como_ruta(valor: object) -> Path | None:
    """Convierte `str` o `os.PathLike` (de texto) en `Path`; devuelve None si no es una ruta usable."""
    try:
        texto = os.fspath(valor)  # type: ignore[call-overload]
    except TypeError:
        return None
    if not isinstance(texto, str) or not texto.strip() or "\x00" in texto:
        return None  # bytes, vacía, solo espacios o con byte nulo
    return Path(texto)


def _clave(ruta: Path) -> Path:
    """Ruta normalizada para comparar: en Windows ignora mayúsculas y unifica separadores."""
    return Path(os.path.normcase(ruta))


def check_data_policy(
    provider_name: str,
    notes_dir: str | os.PathLike | None,
    repo_root: str | os.PathLike | None = None,
) -> None:
    """Lanza `DataPolicyError` si `provider_name` no puede leer `notes_dir`; si es válido, no devuelve nada.

    - `ollama` (tras strip y minúsculas): cualquier carpeta es válida y `notes_dir` ni se examina.
    - Cualquier otro nombre es nube: `notes_dir`, resuelta, debe ser `<repo_root>/fixtures` o estar dentro.
    - `repo_root` por defecto es la raíz de este repositorio (`packages/harness/gabinete_harness/policy.py` -> 3 niveles arriba).

    Pásale el `name` del proveedor realmente instanciado, no un texto de configuración que pudiera no coincidir.
    """
    proveedor = _normalizar_proveedor(provider_name)
    if proveedor == PROVEEDOR_LOCAL:
        return

    prefijo = f"Política D10: el proveedor {_etiqueta(proveedor)} no es local"

    notas = _como_ruta(notes_dir)
    if notas is None:
        raise DataPolicyError(f"{prefijo} y no se indicó una carpeta de notas válida; se rechaza.")

    try:
        raiz = Path(__file__).resolve().parents[3] if repo_root is None else _como_ruta(repo_root)
        if raiz is None:
            raise DataPolicyError(f"{prefijo} y la raíz del repositorio no es una ruta válida; se rechaza.")
        permitida = raiz.resolve() / CARPETA_NUBE  # `fixtures` sin resolver: ver nota del módulo
        notas_resueltas = notas.resolve()  # strict=False: resuelve `..` y enlaces, aunque la ruta aún no exista
    except DataPolicyError:
        raise
    except (OSError, ValueError, RuntimeError):
        # No se encadena la excepción original: su texto suele traer la ruta completa.
        raise DataPolicyError(f"{prefijo} y no se pudo verificar la carpeta de notas; se rechaza.") from None

    if not _clave(notas_resueltas).is_relative_to(_clave(permitida)):
        raise DataPolicyError(
            f"{prefijo} y la carpeta de notas queda fuera de {CARPETA_NUBE}/; "
            f"solo {PROVEEDOR_LOCAL} puede leer datos fuera de {CARPETA_NUBE}/."
        )
