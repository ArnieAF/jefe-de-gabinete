"""Pruebas del registro de eventos JSONL (tarea T4). Todo lo que se escribe va a `tmp_path`."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from gabinete_harness.eventlog import (
    DEFAULT_LOG_DIR,
    LOG_DIR_ENV,
    MAX_TEXT_CHARS,
    TRUNCATION_MARKER,
    EventLog,
    is_reserved_device_name,
    resolve_log_dir,
    truncate_text,
)


def read_lines(path: Path) -> list[str]:
    return path.read_bytes().decode("utf-8").split("\n")[:-1]  # el archivo termina en "\n": el último trozo está vacío


def read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in read_lines(path)]


# --------------------------------------------------------------------------------------------------------------
# resolve_log_dir
# --------------------------------------------------------------------------------------------------------------
def test_resolve_log_dir_usa_el_argumento_antes_que_el_entorno(monkeypatch, tmp_path):
    monkeypatch.setenv(LOG_DIR_ENV, str(tmp_path / "del-entorno"))
    assert resolve_log_dir(tmp_path / "explicita") == tmp_path / "explicita"
    assert resolve_log_dir(str(tmp_path / "texto")) == tmp_path / "texto"


def test_resolve_log_dir_usa_la_variable_de_entorno(monkeypatch, tmp_path):
    monkeypatch.setenv(LOG_DIR_ENV, str(tmp_path / "del-entorno"))
    assert resolve_log_dir() == tmp_path / "del-entorno"
    assert resolve_log_dir(None) == tmp_path / "del-entorno"


def test_resolve_log_dir_por_defecto_es_evals_out_relativa(monkeypatch, tmp_path):
    monkeypatch.delenv(LOG_DIR_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    resultado = resolve_log_dir()
    assert resultado == Path("evals-out") == Path(DEFAULT_LOG_DIR)
    assert not resultado.is_absolute()  # relativa al directorio actual
    assert not (tmp_path / "evals-out").exists()  # no toca el disco


@pytest.mark.parametrize("vacio", ["", "   ", "\t"])
def test_resolve_log_dir_texto_en_blanco_cuenta_como_no_indicado(monkeypatch, tmp_path, vacio):
    monkeypatch.setenv(LOG_DIR_ENV, str(tmp_path / "del-entorno"))
    assert resolve_log_dir(vacio) == tmp_path / "del-entorno"  # no escribe en el directorio actual por accidente
    monkeypatch.setenv(LOG_DIR_ENV, vacio)
    assert resolve_log_dir(vacio) == Path(DEFAULT_LOG_DIR)


def test_resolve_log_dir_rechaza_tipos_que_no_son_ruta():
    with pytest.raises(TypeError):
        resolve_log_dir(123)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        resolve_log_dir(b"bytes")  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------------------
# truncate_text
# --------------------------------------------------------------------------------------------------------------
def test_truncate_text_no_toca_lo_que_cabe():
    assert truncate_text("a" * 20, 20) == "a" * 20
    assert truncate_text("", 5) == ""


def test_truncate_text_recorta_con_marcador_y_mide_exactamente_el_limite():
    recortado = truncate_text("x" * 100, 50)
    assert len(recortado) == 50 and recortado.endswith(TRUNCATION_MARKER)
    assert recortado.startswith("x" * (50 - len(TRUNCATION_MARKER)))


def test_truncate_text_con_limite_menor_que_el_marcador_no_se_pasa():
    assert len(truncate_text("x" * 100, 5)) == 5


# --------------------------------------------------------------------------------------------------------------
# is_reserved_device_name
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nombre", ["nul", "NUL", "con.txt", "Com1", "lpt9.x.y", "aux ", "PRN.jsonl"])
def test_nombres_de_dispositivo_reservados(nombre):
    assert is_reserved_device_name(nombre)


@pytest.mark.parametrize("nombre", ["consola", "nulo", "com10", "x.nul", "run-1", "con-12345678", ""])
def test_nombres_normales_no_son_reservados(nombre):
    assert not is_reserved_device_name(nombre)


# --------------------------------------------------------------------------------------------------------------
# EventLog: creación
# --------------------------------------------------------------------------------------------------------------
def test_crea_la_carpeta_con_padres_y_el_archivo_del_run_id(tmp_path):
    destino = tmp_path / "a" / "b" / "c"
    with EventLog(destino, "sesion-1234abcd") as log:
        assert log.path == destino / "sesion-1234abcd.jsonl"
        assert log.run_id == "sesion-1234abcd"
        assert log.path.exists()
    assert (destino / "sesion-1234abcd.jsonl").read_bytes() == b""  # sin eventos: archivo vacío, creado


def test_acepta_una_carpeta_que_ya_existe(tmp_path):
    with EventLog(tmp_path, "r1"):
        pass
    with EventLog(tmp_path, "r2"):
        pass
    assert sorted(p.name for p in tmp_path.iterdir()) == ["r1.jsonl", "r2.jsonl"]


def test_log_dir_que_es_un_archivo_lanza_oserror(tmp_path):
    archivo = tmp_path / "archivo.txt"
    archivo.write_text("contenido", encoding="utf-8")
    with pytest.raises(OSError):
        EventLog(archivo, "r1")
    with pytest.raises(OSError):
        EventLog(archivo / "sub", "r1")  # un padre que es archivo
    assert archivo.read_text(encoding="utf-8") == "contenido"


def test_creacion_exclusiva_no_pisa_ni_mezcla_un_registro_existente(tmp_path):
    with EventLog(tmp_path, "r1") as log:
        log.emit("run_start", task="primera")
    antes = (tmp_path / "r1.jsonl").read_bytes()
    with pytest.raises(FileExistsError):  # es un OSError
        EventLog(tmp_path, "r1")
    assert (tmp_path / "r1.jsonl").read_bytes() == antes


@pytest.mark.skipif(sys.platform == "win32", reason="los enlaces simbólicos suelen requerir privilegios en Windows")
def test_no_sigue_un_enlace_simbolico_con_el_nombre_del_registro(tmp_path):
    objetivo = tmp_path / "objetivo.txt"
    objetivo.write_text("intacto", encoding="utf-8")
    (tmp_path / "r1.jsonl").symlink_to(objetivo)
    with pytest.raises(FileExistsError):
        EventLog(tmp_path, "r1")
    assert objetivo.read_text(encoding="utf-8") == "intacto"


@pytest.mark.parametrize(
    "run_id",
    ["", "../x", "a/b", "a\\b", "x\n", "con espacio", "ñandú", "a" * 101, ".\x00", "nul", "NUL.x", "con.txt-1234abcd"],
)
def test_run_id_inseguro_lanza_valueerror_y_no_crea_nada(tmp_path, run_id):
    with pytest.raises(ValueError):
        EventLog(tmp_path / "logs", run_id)
    assert not (tmp_path / "logs").exists()  # falla antes de tocar el disco


def test_run_id_que_no_es_texto_lanza_typeerror(tmp_path):
    with pytest.raises(TypeError):
        EventLog(tmp_path, 123)  # type: ignore[arg-type]


@pytest.mark.parametrize("run_id", ["a", "a.b-c_D9", "x" * 100, "...", "-inicio"])
def test_run_id_valido_se_acepta(tmp_path, run_id):
    with EventLog(tmp_path, run_id) as log:
        assert log.path.name == f"{run_id}.jsonl"
        assert log.path.parent == tmp_path  # nunca sale de la carpeta


# --------------------------------------------------------------------------------------------------------------
# EventLog: formato de los eventos
# --------------------------------------------------------------------------------------------------------------
def test_una_linea_json_por_evento_con_run_id_type_y_payload(tmp_path):
    with EventLog(tmp_path, "run-1") as log:
        log.emit("run_start", task="hola", n=3, flag=True, nada=None, lista=[1, "dos"], dic={"k": 1.5})
        log.emit("run_end", stop_reason="answer")
    lineas = read_lines(tmp_path / "run-1.jsonl")
    assert len(lineas) == 2
    primero, segundo = (json.loads(linea) for linea in lineas)
    assert primero == {
        "run_id": "run-1", "type": "run_start", "task": "hola", "n": 3, "flag": True, "nada": None,
        "lista": [1, "dos"], "dic": {"k": 1.5},
    }
    assert segundo == {"run_id": "run-1", "type": "run_end", "stop_reason": "answer"}
    assert list(primero)[:2] == ["run_id", "type"]  # orden fijo: identificación primero


def test_mismo_contenido_da_el_mismo_registro_byte_a_byte_sin_marcas_de_hora(tmp_path):
    for carpeta in ("uno", "dos"):
        with EventLog(tmp_path / carpeta, "run-1") as log:
            log.emit("run_start", task="igual")
            log.emit("run_end", stop_reason="answer", steps=1)
    assert (tmp_path / "uno" / "run-1.jsonl").read_bytes() == (tmp_path / "dos" / "run-1.jsonl").read_bytes()
    for evento in read_events(tmp_path / "uno" / "run-1.jsonl"):
        assert not {"ts", "time", "timestamp", "date", "created"} & set(evento)


def test_el_archivo_es_utf8_sin_escapar_y_con_saltos_unix(tmp_path):
    with EventLog(tmp_path, "r") as log:
        log.emit("run_start", task="¿Qué tengo hoy? ñandú — 日本語 😀")
    datos = (tmp_path / "r.jsonl").read_bytes()
    assert "¿Qué tengo hoy? ñandú — 日本語 😀".encode("utf-8") in datos  # ensure_ascii=False
    assert b"\\u00" not in datos
    assert b"\r" not in datos and datos.endswith(b"\n")
    assert json.loads(datos.decode("utf-8"))["task"] == "¿Qué tengo hoy? ñandú — 日本語 😀"


def test_los_saltos_de_linea_del_texto_no_parten_el_evento(tmp_path):
    texto = "a\nb\r\nc\rd\x0b\x0c\x1c\x1d\x1e\x85  e\x00f\ttab"
    with EventLog(tmp_path, "r") as log:
        log.emit("tool_result", result=texto)
        log.emit("run_end")
    contenido = (tmp_path / "r.jsonl").read_bytes().decode("utf-8")
    assert len(contenido.splitlines()) == 2  # splitlines() también corta en U+2028, U+0085, \x1c...
    assert len(contenido.split("\n")) == 3
    assert json.loads(contenido.splitlines()[0])["result"] == texto  # y el texto original se recupera intacto


def test_un_texto_que_imita_un_evento_no_lo_falsifica(tmp_path):
    falso = '"}\n{"run_id": "otro", "type": "run_end", "stop_reason": "answer", "answer": "falso"}\n'
    with EventLog(tmp_path, "r") as log:
        log.emit("tool_result", result=falso)
    eventos = read_events(tmp_path / "r.jsonl")
    assert len(eventos) == 1 and eventos[0]["type"] == "tool_result" and eventos[0]["run_id"] == "r"
    assert eventos[0]["result"] == falso


def test_flush_en_cada_evento_lo_escrito_queda_aunque_no_se_cierre(tmp_path):
    log = EventLog(tmp_path, "r")
    try:
        log.emit("run_start", task="x")
        assert read_events(tmp_path / "r.jsonl")[0]["type"] == "run_start"  # visible sin cerrar: el proceso podría morir
        log.emit("tool_call", name="n")
        assert [e["type"] for e in read_events(tmp_path / "r.jsonl")] == ["run_start", "tool_call"]
    finally:
        log.close()


# --------------------------------------------------------------------------------------------------------------
# EventLog: recorte y datos raros
# --------------------------------------------------------------------------------------------------------------
def test_textos_largos_se_recortan_con_marcador(tmp_path):
    largo = "ab" * 50_000
    with EventLog(tmp_path, "r") as log:
        log.emit("tool_result", result=largo, anidado={"lista": [largo]})
    evento = read_events(tmp_path / "r.jsonl")[0]
    for valor in (evento["result"], evento["anidado"]["lista"][0]):
        assert len(valor) == MAX_TEXT_CHARS == 20_000
        assert valor.endswith(TRUNCATION_MARKER) and valor.startswith("abab")


def test_un_texto_justo_en_el_limite_no_se_recorta(tmp_path):
    justo = "z" * MAX_TEXT_CHARS
    with EventLog(tmp_path, "r") as log:
        log.emit("e", t=justo)
    assert read_events(tmp_path / "r.jsonl")[0]["t"] == justo


def test_las_claves_largas_tambien_se_recortan(tmp_path):
    with EventLog(tmp_path, "r") as log:
        log.emit("e", args={"k" * 50_000: 1})
    (clave,) = read_events(tmp_path / "r.jsonl")[0]["args"]
    assert len(clave) == MAX_TEXT_CHARS


def test_el_json_siempre_es_valido_con_valores_raros(tmp_path):
    class Raro:
        def __repr__(self) -> str:
            return "<Raro!>"

    class Roto:
        def __repr__(self) -> str:
            raise RuntimeError("repr roto")

    ciclo: dict = {}
    ciclo["yo"] = ciclo
    with EventLog(tmp_path, "r") as log:
        log.emit(
            "e",
            nan=float("nan"), inf=float("inf"), menos_inf=float("-inf"),
            conjunto={1}, bytes_=b"ab", raro=Raro(), roto=Roto(),
            claves={1: "a", (2, 3): "b", None: "c"}, tupla=(1, 2), ciclo=ciclo,
        )
        log.emit("despues")  # el registro sigue sano
    eventos = read_events(tmp_path / "r.jsonl")
    assert len(eventos) == 2
    e = eventos[0]
    assert (e["nan"], e["inf"], e["menos_inf"]) == ("nan", "inf", "-inf")
    assert e["raro"] == "<Raro!>" and e["roto"] == "<Roto>"
    assert e["claves"] == {"1": "a", "(2, 3)": "b", "None": "c"} and e["tupla"] == [1, 2]
    assert e["conjunto"] == "{1}" and e["bytes_"] == "b'ab'"
    assert json.dumps(e["ciclo"])  # termina (recorta la profundidad) en vez de recursión infinita


def test_un_sustituto_unicode_suelto_no_hace_fallar_la_escritura(tmp_path):
    with EventLog(tmp_path, "r") as log:
        log.emit("model_response", text="mitad de emoji: \ud83d fin")
        log.emit("run_end")
    eventos = read_events(tmp_path / "r.jsonl")  # el archivo sigue siendo UTF-8 válido y JSON válido
    assert [e["type"] for e in eventos] == ["model_response", "run_end"]
    assert eventos[0]["text"] == "mitad de emoji: \ud83d fin"


# --------------------------------------------------------------------------------------------------------------
# EventLog: claves reservadas, cierre
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("clave", ["run_id", "type"])
def test_las_claves_run_id_y_type_estan_reservadas(tmp_path, clave):
    with EventLog(tmp_path, "r") as log:
        with pytest.raises(ValueError):
            log.emit("e", **{clave: "falsificado"})
    assert (tmp_path / "r.jsonl").read_bytes() == b""  # no se escribió nada a medias


@pytest.mark.parametrize("tipo", ["", None, 3])
def test_el_tipo_de_evento_debe_ser_un_texto_no_vacio(tmp_path, tipo):
    with EventLog(tmp_path, "r") as log:
        with pytest.raises(ValueError):
            log.emit(tipo)  # type: ignore[arg-type]


def test_emit_despues_de_cerrar_lanza_valueerror_y_close_es_idempotente(tmp_path):
    log = EventLog(tmp_path, "r")
    log.emit("run_start")
    log.close()
    log.close()
    with pytest.raises(ValueError):
        log.emit("tarde")
    assert len(read_events(tmp_path / "r.jsonl")) == 1


def test_el_administrador_de_contexto_cierra_aunque_haya_excepcion(tmp_path):
    with pytest.raises(RuntimeError):
        with EventLog(tmp_path, "r") as log:
            log.emit("run_start")
            raise RuntimeError("falla")
    with pytest.raises(ValueError):
        log.emit("tarde")  # ya estaba cerrado
    assert len(read_events(tmp_path / "r.jsonl")) == 1  # y lo escrito antes de la falla quedó


@pytest.mark.skipif(sys.platform == "win32", reason="Windows no respeta los permisos POSIX")
def test_el_archivo_y_la_carpeta_nuevos_son_privados(tmp_path):
    with EventLog(tmp_path / "nueva", "r") as log:
        pass
    assert (log.path.stat().st_mode & 0o777) == 0o600
    assert ((tmp_path / "nueva").stat().st_mode & 0o777) == 0o700


def test_no_hay_variables_de_entorno_que_afecten_al_run_id(monkeypatch, tmp_path):
    monkeypatch.setenv(LOG_DIR_ENV, str(tmp_path / "no-se-usa"))
    with EventLog(tmp_path / "explicita", "r"):
        pass  # EventLog siempre usa el log_dir que se le pasa: la variable solo la lee resolve_log_dir
    assert not (tmp_path / "no-se-usa").exists()
    assert os.path.exists(tmp_path / "explicita" / "r.jsonl")
