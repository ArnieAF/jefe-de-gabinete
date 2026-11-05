"""Pruebas de la clave opcional `limites` de los casos de eval (ampliación de cases.py en la tarea T8)."""
import dataclasses
from pathlib import Path

import pytest

from gabinete_evals.cases import Case, Expect, Limites, load_cases


def escribir(carpeta: Path, nombre: str, texto: str) -> Path:
    ruta = carpeta / nombre
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def caso_con_limites(limites: str | None) -> str:
    """Un caso mínimo válido; `limites` es el texto YAML de la clave (None = sin la clave)."""
    base = '- id: c1\n  pregunta: "p"\n  esperado: { stop_reason: max_steps }\n'
    return base if limites is None else base + f"  limites: {limites}\n"


def cargar(tmp_path, limites: str | None) -> Case:
    return load_cases(escribir(tmp_path, "l.yaml", caso_con_limites(limites)))[0]


def error(tmp_path, limites: str, nombre: str = "malo.yaml") -> str:
    with pytest.raises(ValueError) as info:
        load_cases(escribir(tmp_path, nombre, caso_con_limites(limites)))
    return str(info.value)


# --- carga correcta ---------------------------------------------------------------------------------


def test_sin_limites_el_valor_es_none(tmp_path):
    assert cargar(tmp_path, None).limites is None


def test_solo_max_steps(tmp_path):
    assert cargar(tmp_path, "{ max_steps: 3 }").limites == Limites(max_steps=3, max_cost_usd=None)


def test_solo_max_cost_usd(tmp_path):
    assert cargar(tmp_path, "{ max_cost_usd: 1.5 }").limites == Limites(max_steps=None, max_cost_usd=1.5)


def test_ambos_limites_en_bloque_yaml(tmp_path):
    texto = '- id: c1\n  pregunta: "p"\n  esperado: { stop_reason: max_cost }\n  limites:\n    max_steps: 2\n    max_cost_usd: 1.0\n'
    c = load_cases(escribir(tmp_path, "l.yaml", texto))[0]
    assert c.limites == Limites(max_steps=2, max_cost_usd=1.0)


def test_el_costo_entero_se_guarda_como_float_y_cero_es_valido(tmp_path):
    costo = cargar(tmp_path, "{ max_cost_usd: 2 }").limites.max_cost_usd
    assert costo == 2.0 and isinstance(costo, float)
    cero = cargar(tmp_path, "{ max_cost_usd: 0 }").limites.max_cost_usd
    assert cero == 0.0 and isinstance(cero, float)  # 0 = sin límite, igual que en run()


def test_limites_se_conserva_tambien_en_raw(tmp_path):
    assert cargar(tmp_path, "{ max_steps: 3 }").raw["limites"] == {"max_steps": 3}


def test_limites_default_de_la_dataclass():
    assert Limites() == Limites(max_steps=None, max_cost_usd=None)


# --- compatibilidad: Case conserva sus campos y valores por defecto ---------------------------------


def test_case_conserva_campos_y_orden():
    nombres = [f.name for f in dataclasses.fields(Case)]
    # los campos de T7, en su orden original, y `limites` solo al final
    assert nombres == ["id", "capa", "pregunta", "esperado", "repeticiones", "guion", "raw", "limites"]


def test_case_se_construye_como_antes_de_t8():
    c = Case("x", "capa", "p", Expect(contiene=["a"]))
    assert (c.repeticiones, c.guion, c.raw, c.limites) == (1, None, {}, None)
    c2 = Case("x", "capa", "p", Expect(contiene=["a"]), 2, [{"text": "hola"}], {"id": "x"})  # posicional, como en T7
    assert (c2.repeticiones, c2.guion, c2.raw, c2.limites) == (2, [{"text": "hola"}], {"id": "x"}, None)


# --- errores de validación --------------------------------------------------------------------------


def test_clave_desconocida_indica_archivo_id_y_permitidas(tmp_path):
    msg = error(tmp_path, "{ max_steps: 3, max_step: 4 }")
    assert "malo.yaml" in msg and "'c1'" in msg
    assert "claves desconocidas" in msg and "max_step" in msg and "max_cost_usd" in msg


def test_clave_desconocida_aunque_las_validas_esten_bien(tmp_path):
    msg = error(tmp_path, "{ max_cost: 1.0 }")  # errata: falta "_usd"
    assert "max_cost" in msg and "limites" in msg


@pytest.mark.parametrize("valor", ["0", "-1", "2.5", '"3"', "true", "false", "null", "[3]", ".inf", ".nan"])
def test_max_steps_invalido(tmp_path, valor):
    msg = error(tmp_path, "{ max_steps: %s }" % valor)
    assert "max_steps" in msg and "c1" in msg and "malo.yaml" in msg


@pytest.mark.parametrize("valor", ["-0.5", "-1", '"1.0"', "true", "false", "null", "[1]", ".inf", "-.inf", ".nan"])
def test_max_cost_usd_invalido(tmp_path, valor):
    msg = error(tmp_path, "{ max_cost_usd: %s }" % valor)
    assert "max_cost_usd" in msg and "c1" in msg and "malo.yaml" in msg


def test_max_cost_usd_entero_gigante_no_desborda(tmp_path):
    msg = error(tmp_path, "{ max_cost_usd: %s }" % ("9" * 400))  # float() de un entero así lanzaría OverflowError
    assert "max_cost_usd" in msg and "c1" in msg


@pytest.mark.parametrize("valor", ["[3]", "3", '"max_steps"', "true"])
def test_limites_debe_ser_un_mapa(tmp_path, valor):
    msg = error(tmp_path, valor)
    assert "limites" in msg and "mapa" in msg and "c1" in msg


@pytest.mark.parametrize("valor", ["{}", "null"])
def test_limites_vacio_o_nulo_se_rechaza(tmp_path, valor):
    # un `limites` que no limita nada es casi seguro un error de escritura
    msg = error(tmp_path, valor)
    assert "limites" in msg and "c1" in msg


def test_el_error_de_un_caso_de_la_carpeta_no_se_traga_en_silencio(tmp_path):
    escribir(tmp_path, "a.yaml", caso_con_limites("{ max_steps: 3 }"))
    escribir(tmp_path, "b.yaml", caso_con_limites("{ max_steps: 0 }").replace("id: c1", "id: c2"))
    with pytest.raises(ValueError) as info:
        load_cases(tmp_path)
    assert "b.yaml" in str(info.value) and "c2" in str(info.value)
