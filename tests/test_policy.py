"""Pruebas del guardián de privacidad D10 (tarea T6).

Se piensa como atacante: rutas con `..`, carpetas hermanas con prefijo parecido, enlaces que salen de `fixtures/`,
nombres de proveedor disfrazados, entradas raras y mensajes que no deben filtrar la ruta.
Los repos de prueba son falsos (carpetas bajo `tmp_path`); solo la última sección usa el repo real.
"""
from __future__ import annotations

import inspect
import os
import subprocess
import sys
import traceback
from pathlib import Path

import pytest

from gabinete_harness import policy
from gabinete_harness.policy import DataPolicyError, check_data_policy

NUBES = ["gemini", "anthropic", "scripted", "", "desconocido"]
SECRETO = "datos-de-usuario-secreto"  # nombre que jamás debe aparecer en un mensaje de error


# ---------------------------------------------------------------- ayudas

@pytest.fixture
def repo_falso(tmp_path: Path) -> Path:
    """Repo falso con `fixtures/vault` adentro y, afuera, una carpeta de "datos reales"."""
    raiz = tmp_path / "repo"
    (raiz / "fixtures" / "vault").mkdir(parents=True)
    (raiz / "real").mkdir()
    (tmp_path / SECRETO / "notas").mkdir(parents=True)
    return raiz


@pytest.fixture
def afuera(repo_falso: Path) -> Path:
    """Carpeta con "notas reales", fuera del repo falso."""
    return repo_falso.parent / SECRETO / "notas"


def _enlazar(enlace: Path, objetivo: Path) -> None:
    """Crea un enlace de directorio `enlace -> objetivo`.

    Intenta un enlace simbólico; en Windows, sin privilegios, cae a una unión (`mklink /J`), que `resolve()` también sigue.
    Si ninguna es posible, salta la prueba.
    """
    try:
        os.symlink(objetivo, enlace, target_is_directory=True)
    except (OSError, NotImplementedError):
        creada = False
        if os.name == "nt":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(objetivo)], capture_output=True)
            creada = r.returncode == 0
        if not creada:
            pytest.skip("el sistema no permite crear enlaces simbólicos ni uniones")
    assert enlace.resolve() == objetivo.resolve(), "el enlace de prueba no se resuelve: la prueba no sería válida"


def _es_error(proveedor: object, carpeta: object, raiz: Path | str | None) -> bool:
    try:
        check_data_policy(proveedor, carpeta, raiz)  # type: ignore[arg-type]
    except DataPolicyError:
        return True
    return False


# ---------------------------------------------------------------- ollama

def test_ollama_puede_leer_fuera_de_fixtures(repo_falso: Path, afuera: Path):
    assert check_data_policy("ollama", afuera, repo_falso) is None
    assert check_data_policy("ollama", str(afuera), repo_falso) is None
    assert check_data_policy("ollama", repo_falso, repo_falso) is None


def test_ollama_no_examina_la_carpeta(repo_falso: Path):
    """Con ollama cualquier valor de `notes_dir` es válido y no se toca."""
    for carpeta in (None, "", "   ", 123, b"bytes", "con\x00nulo"):
        assert check_data_policy("ollama", carpeta, repo_falso) is None  # type: ignore[arg-type]


def test_ollama_con_el_repo_por_defecto(tmp_path: Path):
    assert check_data_policy("ollama", tmp_path) is None


# ---------------------------------------------------------------- nubes

@pytest.mark.parametrize("proveedor", NUBES)
def test_nube_con_carpeta_fuera_de_fixtures_da_error(proveedor: str, repo_falso: Path, afuera: Path):
    with pytest.raises(DataPolicyError) as exc:
        check_data_policy(proveedor, afuera, repo_falso)
    assert repr(proveedor) in str(exc.value)  # el mensaje indica el proveedor
    assert "fixtures" in str(exc.value)  # y el motivo


@pytest.mark.parametrize("proveedor", NUBES)
def test_nube_con_fixtures_es_valida(proveedor: str, repo_falso: Path):
    assert check_data_policy(proveedor, repo_falso / "fixtures", repo_falso) is None
    assert check_data_policy(proveedor, repo_falso / "fixtures" / "vault", repo_falso) is None
    assert check_data_policy(proveedor, str(repo_falso / "fixtures" / "vault"), repo_falso) is None


def test_nube_con_subcarpeta_de_fixtures_que_aun_no_existe(repo_falso: Path):
    nueva = repo_falso / "fixtures" / "vault" / "aun" / "no" / "existe"
    assert not nueva.exists()
    assert check_data_policy("gemini", nueva, repo_falso) is None


def test_repo_root_acepta_texto_y_path(repo_falso: Path):
    carpeta = repo_falso / "fixtures" / "vault"
    assert check_data_policy("gemini", carpeta, str(repo_falso)) is None
    assert check_data_policy("gemini", carpeta, repo_falso) is None


def test_tolera_puntos_y_barras_redundantes_dentro_de_fixtures(repo_falso: Path):
    assert check_data_policy("gemini", str(repo_falso / "fixtures" / ".") + os.sep, repo_falso) is None
    assert check_data_policy("gemini", repo_falso / "fixtures" / "vault" / ".." / "vault", repo_falso) is None


# ---------------------------------------------------------------- nombre del proveedor

@pytest.mark.parametrize("nombre", ["  OLLAMA ", "Ollama", " ollama\n", "\tOLLAMA\t"])
def test_el_nombre_de_ollama_se_normaliza(nombre: str, repo_falso: Path, afuera: Path):
    assert check_data_policy(nombre, afuera, repo_falso) is None


@pytest.mark.parametrize("nombre", ["Gemini", "  GEMINI ", "Anthropic", " Scripted "])
def test_el_nombre_de_una_nube_se_normaliza_y_sigue_siendo_nube(nombre: str, repo_falso: Path, afuera: Path):
    assert _es_error(nombre, afuera, repo_falso)
    assert check_data_policy(nombre, repo_falso / "fixtures", repo_falso) is None


@pytest.mark.parametrize(
    "nombre",
    [
        "ollama2", "ollama-cloud", "ollama:latest", "ollama cloud", "ollam", "o11ama", "llama",
        "ollama\x00", "ollаma",  # а = "а" cirílica
        "ｏｌｌａｍａ",  # "ollama" en caracteres de ancho completo
        "ollama​",  # espacio de ancho cero: strip no lo quita
    ],
)
def test_solo_el_nombre_exacto_ollama_es_local(nombre: str, repo_falso: Path, afuera: Path):
    assert _es_error(nombre, afuera, repo_falso)


@pytest.mark.parametrize("nombre", [None, 5, b"ollama", ["ollama"]])
def test_un_proveedor_que_no_es_texto_se_trata_como_nube(nombre: object, repo_falso: Path, afuera: Path):
    assert _es_error(nombre, afuera, repo_falso)
    assert check_data_policy(nombre, repo_falso / "fixtures", repo_falso) is None  # type: ignore[arg-type]


def test_el_nombre_largo_o_con_saltos_de_linea_no_ensucia_el_mensaje(repo_falso: Path, afuera: Path):
    nombre = "gem\nini\r" + "x" * 500
    with pytest.raises(DataPolicyError) as exc:
        check_data_policy(nombre, afuera, repo_falso)
    mensaje = str(exc.value)
    assert "\n" not in mensaje and "\r" not in mensaje
    assert len(mensaje) < 300


# ---------------------------------------------------------------- escapes por ruta

@pytest.mark.parametrize(
    "relativa",
    [
        "fixtures/../real",
        "fixtures/vault/../../real",
        "fixtures/no-existe/../../real",  # componente intermedio que no existe
        "fixtures/..",
        "fixtures/vault/../..",
        "fixtures/../fixtures-real",
        ".",
        "real",
    ],
)
def test_escapes_con_punto_punto_dan_error(relativa: str, repo_falso: Path):
    assert _es_error("gemini", repo_falso / relativa, repo_falso)
    assert _es_error("gemini", str(repo_falso) + os.sep + relativa.replace("/", os.sep), repo_falso)


@pytest.mark.parametrize("nombre", ["fixtures-real", "fixtures2", "fixtures.bak", "fixturesX", "Xfixtures", "fixtures_"])
def test_carpeta_hermana_con_prefijo_parecido_da_error(nombre: str, repo_falso: Path):
    hermana = repo_falso / nombre
    hermana.mkdir()
    assert _es_error("gemini", hermana, repo_falso)
    assert _es_error("gemini", hermana / "vault", repo_falso)


def test_un_startswith_ingenuo_habria_dejado_pasar_a_la_hermana(repo_falso: Path):
    """Documenta el ataque: por texto `fixtures-real` empieza igual que `fixtures`; por componentes no está dentro."""
    hermana = repo_falso / "fixtures-real"
    hermana.mkdir()
    assert str(hermana).startswith(str(repo_falso / "fixtures"))
    assert _es_error("gemini", hermana, repo_falso)


def test_fixtures_de_otro_repo_da_error(repo_falso: Path):
    otro = repo_falso.parent / "otro-repo" / "fixtures"
    otro.mkdir(parents=True)
    assert _es_error("gemini", otro, repo_falso)


def test_el_padre_y_la_raiz_del_repo_dan_error(repo_falso: Path):
    assert _es_error("gemini", repo_falso, repo_falso)
    assert _es_error("gemini", repo_falso.parent, repo_falso)
    assert _es_error("gemini", repo_falso.anchor or os.sep, repo_falso)


# ---------------------------------------------------------------- enlaces

def test_enlace_dentro_de_fixtures_que_apunta_afuera_da_error(repo_falso: Path, afuera: Path):
    enlace = repo_falso / "fixtures" / "vault-enlazado"
    _enlazar(enlace, afuera)
    assert _es_error("gemini", enlace, repo_falso)
    assert _es_error("gemini", enlace / "subcarpeta-que-no-existe", repo_falso)
    assert check_data_policy("ollama", enlace, repo_falso) is None  # ollama sigue pudiendo


def test_enlace_dentro_de_fixtures_que_apunta_a_otro_lugar_de_fixtures_es_valido(repo_falso: Path):
    (repo_falso / "fixtures" / "a").mkdir()
    enlace = repo_falso / "fixtures" / "atajo"
    _enlazar(enlace, repo_falso / "fixtures" / "a")
    assert check_data_policy("gemini", enlace, repo_falso) is None


def test_enlace_hacia_fixtures_desde_afuera_es_valido_porque_se_resuelve(repo_falso: Path, tmp_path: Path):
    enlace = tmp_path / "atajo-a-fixtures"
    _enlazar(enlace, repo_falso / "fixtures")
    assert check_data_policy("gemini", enlace, repo_falso) is None


def test_si_fixtures_mismo_es_un_enlace_hacia_afuera_se_rechaza(tmp_path: Path, afuera: Path):
    """Falla cerrado: una carpeta `fixtures` que en realidad es otro lugar no puede abrirle la puerta a datos reales."""
    raiz = tmp_path / "repo-con-fixtures-enlazado"
    raiz.mkdir()
    _enlazar(raiz / "fixtures", afuera)
    assert _es_error("gemini", raiz / "fixtures", raiz)
    assert _es_error("gemini", raiz / "fixtures" / "algo", raiz)


def test_el_enlace_seguido_de_punto_punto_se_decide_como_lo_abre_el_sistema(repo_falso: Path, afuera: Path):
    """`fixtures/enlace/../x`: POSIX sigue el enlace y sube desde su destino; Windows normaliza el `..` antes.

    El resultado de la política debe coincidir con la carpeta que el sistema operativo realmente abre.
    """
    (afuera.parent / "x").mkdir()  # `x` junto al destino del enlace (afuera/notas -> afuera/x al subir)
    (repo_falso / "fixtures" / "x").mkdir()
    enlace = repo_falso / "fixtures" / "enlace"
    _enlazar(enlace, afuera)
    ruta = enlace / ".." / "x"
    abre_fixtures = ruta.samefile(repo_falso / "fixtures" / "x")  # lo que hace el SO de verdad
    assert _es_error("gemini", ruta, repo_falso) is (not abre_fixtures)


# ---------------------------------------------------------------- mayúsculas

@pytest.mark.skipif(os.name != "nt", reason="la insensibilidad a mayúsculas es de Windows")
def test_en_windows_otras_mayusculas_son_la_misma_carpeta(repo_falso: Path):
    assert check_data_policy("gemini", str(repo_falso).upper() + "\\FIXTURES", repo_falso) is None
    assert check_data_policy("gemini", str(repo_falso / "FIXTURES" / "VAULT"), repo_falso) is None
    assert check_data_policy("gemini", str(repo_falso / "fixtures").replace("\\", "/") + "/Vault", repo_falso) is None
    assert check_data_policy("gemini", repo_falso / "Fixtures", str(repo_falso).upper()) is None
    assert _es_error("gemini", str(repo_falso / "FIXTURES-REAL"), repo_falso)  # mayúsculas no hacen pasar a la hermana


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="sistema de archivos sensible a mayúsculas (Linux)")
def test_en_linux_otras_mayusculas_son_otra_carpeta(repo_falso: Path):
    assert _es_error("gemini", repo_falso / "FIXTURES", repo_falso)


# ---------------------------------------------------------------- entradas inválidas (todas fallan cerrado)

@pytest.mark.parametrize("carpeta", [None, "", "   ", "\t\n", "con\x00nulo", 123, 4.5, b"fixtures", object()])
@pytest.mark.parametrize("proveedor", ["gemini", "scripted", ""])
def test_carpeta_invalida_con_una_nube_da_error(proveedor: str, carpeta: object, repo_falso: Path):
    with pytest.raises(DataPolicyError, match="carpeta de notas"):
        check_data_policy(proveedor, carpeta, repo_falso)  # type: ignore[arg-type]


@pytest.mark.parametrize("raiz", ["", "   ", 123, b"repo", "con\x00nulo"])
def test_repo_root_invalido_da_error(raiz: object, repo_falso: Path):
    assert _es_error("gemini", repo_falso / "fixtures", raiz)  # type: ignore[arg-type]


def test_una_ruta_relativa_se_interpreta_desde_el_directorio_actual(repo_falso: Path, afuera: Path, monkeypatch):
    monkeypatch.chdir(repo_falso / "fixtures")
    assert check_data_policy("gemini", "vault", repo_falso) is None
    assert check_data_policy("gemini", ".", repo_falso) is None
    assert _es_error("gemini", "..", repo_falso)
    monkeypatch.chdir(repo_falso)
    assert _es_error("gemini", ".", repo_falso)
    assert _es_error("gemini", "real", repo_falso)
    assert check_data_policy("gemini", "fixtures/vault", repo_falso) is None
    monkeypatch.chdir(afuera)
    assert _es_error("gemini", ".", repo_falso)


def test_un_objeto_pathlike_con_bytes_se_rechaza(repo_falso: Path):
    class RutaBytes:
        def __fspath__(self) -> bytes:
            return bytes(repo_falso / "fixtures")

    assert _es_error("gemini", RutaBytes(), repo_falso)


# ---------------------------------------------------------------- el mensaje no filtra la ruta

def _casos_de_error(repo_falso: Path, afuera: Path) -> list[tuple[str, object]]:
    return [
        ("gemini", afuera),
        ("gemini", repo_falso / "fixtures" / ".." / ".." / SECRETO / "notas"),
        ("anthropic", str(afuera)),
        ("scripted", afuera / "con\x00nulo"),  # byte nulo: entrada inválida
        ("", afuera),
    ]


def test_el_mensaje_de_error_no_contiene_la_ruta(repo_falso: Path, afuera: Path):
    for proveedor, carpeta in _casos_de_error(repo_falso, afuera):
        with pytest.raises(DataPolicyError) as exc:
            check_data_policy(proveedor, carpeta, repo_falso)
        textos = [str(exc.value), repr(exc.value), "".join(traceback.format_exception(exc.value))]
        for texto in textos:
            assert SECRETO not in texto, f"filtró la ruta con {proveedor!r}"
            assert str(afuera.parent) not in texto
            assert str(repo_falso.parent) not in texto
        assert exc.value.__cause__ is None
        assert exc.value.__suppress_context__ or exc.value.__context__ is None


def test_el_mensaje_no_contiene_la_ruta_relativa_de_entrada(repo_falso: Path, monkeypatch):
    monkeypatch.chdir(repo_falso)
    with pytest.raises(DataPolicyError) as exc:
        check_data_policy("gemini", "carpeta-relativa-secreta", repo_falso)
    assert "carpeta-relativa-secreta" not in str(exc.value)


@pytest.mark.parametrize("excepcion", [OSError, ValueError, RuntimeError])
def test_si_el_sistema_falla_al_resolver_se_rechaza_sin_filtrar_la_ruta(excepcion, repo_falso: Path, afuera: Path, monkeypatch):
    """La excepción del sistema suele traer la ruta completa: no debe viajar ni en el mensaje ni encadenada."""

    def falla(self, *args, **kwargs):
        raise excepcion(f"fallo del sistema con {self}")

    monkeypatch.setattr(policy.Path, "resolve", falla)
    with pytest.raises(DataPolicyError, match="no se pudo verificar") as exc:
        check_data_policy("gemini", afuera, repo_falso)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__
    assert SECRETO not in "".join(traceback.format_exception(exc.value))
    assert check_data_policy("ollama", afuera, repo_falso) is None  # ollama no resuelve nada


def test_el_error_nombra_el_motivo_y_el_proveedor(repo_falso: Path, afuera: Path):
    with pytest.raises(DataPolicyError) as exc:
        check_data_policy("Gemini", afuera, repo_falso)
    mensaje = str(exc.value)
    assert "D10" in mensaje and "'gemini'" in mensaje and "fixtures/" in mensaje and "ollama" in mensaje


# ---------------------------------------------------------------- sin forma de saltarse la regla

@pytest.mark.parametrize(
    "variable",
    ["GABINETE_ALLOW_REAL_DATA", "GABINETE_ALLOW_CLOUD", "GABINETE_D10_OFF", "ALLOW_REAL_DATA", "D10_DISABLE", "GABINETE_PROVIDER"],
)
def test_ninguna_variable_de_entorno_cambia_el_resultado(variable: str, monkeypatch, repo_falso: Path, afuera: Path):
    for valor in ("1", "true", "ollama", "yes"):
        monkeypatch.setenv(variable, valor)
        assert _es_error("gemini", afuera, repo_falso)


def test_la_firma_no_tiene_parametros_para_saltarse_la_regla():
    parametros = list(inspect.signature(check_data_policy).parameters)
    assert parametros == ["provider_name", "notes_dir", "repo_root"]
    with pytest.raises(TypeError):
        check_data_policy("gemini", "x", force=True)  # type: ignore[call-arg]


def test_el_modulo_no_lee_variables_de_entorno():
    codigo = Path(policy.__file__).read_text(encoding="utf-8")
    assert "environ" not in codigo and "getenv" not in codigo


def test_data_policy_error_es_una_excepcion_propia():
    assert issubclass(DataPolicyError, Exception)
    assert not issubclass(DataPolicyError, (OSError, ValueError))  # no se confunde con errores del sistema


# ---------------------------------------------------------------- repo real (repo_root por defecto)

def test_repo_root_por_defecto_es_la_raiz_del_repo_real(repo_root: Path):
    assert Path(policy.__file__).resolve().parents[3] == repo_root
    assert (repo_root / "fixtures").is_dir()


def test_con_el_repo_real_fixtures_vault_es_valido_para_una_nube(repo_root: Path):
    assert check_data_policy("gemini", repo_root / "fixtures" / "vault") is None
    assert check_data_policy("scripted", repo_root / "fixtures") is None
    assert check_data_policy("anthropic", str(repo_root / "fixtures" / "vault")) is None


def test_con_el_repo_real_la_raiz_y_otras_carpetas_dan_error(repo_root: Path):
    for carpeta in (repo_root, repo_root / "packages", repo_root / "docs", repo_root / "fixtures" / ".." / "docs", repo_root.parent):
        with pytest.raises(DataPolicyError):
            check_data_policy("gemini", carpeta)
    assert check_data_policy("ollama", repo_root) is None
