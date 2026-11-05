"""Pruebas de la carga de casos de eval (tarea T7)."""
from pathlib import Path

import pytest

from gabinete_evals.cases import Case, Expect, load_cases

CASO_OK = """\
- id: herramienta-eventos-hoy
  capa: herramientas
  guion:
    - { tool_calls: [{ name: "calendar.list_events", arguments: { date: "2026-11-05" } }] }
    - { text: "Hoy tienes la cita con el dentista y la reunión con Rosa Huamán." }
  pregunta: "¿Qué tengo hoy?"
  esperado:
    contiene: ["dentista", "Rosa"]
    no_contiene: []
    herramienta: "calendar.list_events"
    max_pasos: 3
  repeticiones: 2
"""


def escribir(carpeta: Path, nombre: str, texto: str) -> Path:
    ruta = carpeta / nombre
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def caso_yaml(**extra) -> str:
    """Un caso mínimo válido; `extra` pisa o agrega líneas (texto ya en YAML) a nivel del caso."""
    base = {"id": "c1", "capa": "rag", "pregunta": '"¿Hola?"', "esperado": "{ contiene: Lima }"}
    base.update(extra)
    return "\n".join(f"{'-' if i == 0 else ' '} {k}: {v}" for i, (k, v) in enumerate(base.items())) + "\n"


# --- carga correcta ---------------------------------------------------------------------------------


def test_carga_un_archivo(tmp_path):
    cases = load_cases(escribir(tmp_path, "casos.yaml", CASO_OK))
    assert len(cases) == 1
    c = cases[0]
    assert isinstance(c, Case) and isinstance(c.esperado, Expect)
    assert (c.id, c.capa, c.pregunta, c.repeticiones) == ("herramienta-eventos-hoy", "herramientas", "¿Qué tengo hoy?", 2)
    assert c.esperado.contiene == ["dentista", "Rosa"]
    assert c.esperado.no_contiene == []
    assert c.esperado.herramienta == "calendar.list_events"
    assert c.esperado.max_pasos == 3 and c.esperado.stop_reason is None
    assert c.guion is not None and len(c.guion) == 2
    assert c.raw["id"] == "herramienta-eventos-hoy"  # raw conserva el original


def test_carga_una_carpeta_en_orden_alfabetico_e_ignora_otros_archivos(tmp_path):
    escribir(tmp_path, "b.yaml", caso_yaml(id="b1"))
    escribir(tmp_path, "a.yaml", caso_yaml(id="a1") + caso_yaml(id="a2"))
    escribir(tmp_path, "notas.txt", "esto no es YAML de casos: ignorado")
    (tmp_path / "subcarpeta.yaml").mkdir()  # una carpeta llamada *.yaml tampoco cuenta
    assert [c.id for c in load_cases(tmp_path)] == ["a1", "a2", "b1"]


def test_acepta_ruta_como_texto(tmp_path):
    escribir(tmp_path, "c.yaml", caso_yaml())
    assert [c.id for c in load_cases(str(tmp_path / "c.yaml"))] == ["c1"]


def test_valores_por_defecto(tmp_path):
    texto = '- id: x\n  pregunta: "p"\n  esperado: { stop_reason: denied }\n'
    c = load_cases(escribir(tmp_path, "d.yaml", texto))[0]
    assert c.repeticiones == 1 and c.guion is None and c.capa == "sin-capa"
    assert c.esperado.contiene == [] and c.esperado.herramienta is None


def test_contiene_y_no_contiene_texto_se_normalizan_a_lista(tmp_path):
    texto = '- id: x\n  pregunta: "p"\n  esperado: { contiene: Lima, no_contiene: Cusco }\n'
    c = load_cases(escribir(tmp_path, "d.yaml", texto))[0]
    assert c.esperado.contiene == ["Lima"] and c.esperado.no_contiene == ["Cusco"]


def test_acepta_sesiones_del_formato_de_memoria_y_la_guarda_en_raw(tmp_path):
    texto = '- id: m\n  capa: memoria\n  sesiones: ["Vivo en Cusco", "Me mudé a Lima"]\n  pregunta: "p"\n  esperado: { contiene: Lima }\n'
    c = load_cases(escribir(tmp_path, "m.yaml", texto))[0]
    assert c.raw["sesiones"] == ["Vivo en Cusco", "Me mudé a Lima"]


def test_lee_utf8_con_bom(tmp_path):
    (tmp_path / "bom.yaml").write_bytes(b"\xef\xbb\xbf" + caso_yaml(pregunta='"¿Qué tal?"').encode("utf-8"))
    assert load_cases(tmp_path / "bom.yaml")[0].pregunta == "¿Qué tal?"


def test_el_caso_cargado_no_comparte_listas_entre_casos(tmp_path):
    escribir(tmp_path, "a.yaml", caso_yaml(id="a") + caso_yaml(id="b"))
    a, b = load_cases(tmp_path / "a.yaml")
    a.esperado.contiene.append("extra")
    assert b.esperado.contiene == ["Lima"]


# --- errores de validación --------------------------------------------------------------------------


def error(tmp_path, texto: str, nombre: str = "malo.yaml") -> str:
    with pytest.raises(ValueError) as info:
        load_cases(escribir(tmp_path, nombre, texto))
    return str(info.value)


def test_falta_id(tmp_path):
    msg = error(tmp_path, '- capa: rag\n  pregunta: "p"\n  esperado: { contiene: a }\n')
    assert "malo.yaml" in msg and "#1" in msg and "'id'" in msg


def test_id_vacio_o_no_texto(tmp_path):
    assert "'id'" in error(tmp_path, '- id: "  "\n  pregunta: "p"\n  esperado: { contiene: a }\n')
    assert "'id'" in error(tmp_path, '- id: 7\n  pregunta: "p"\n  esperado: { contiene: a }\n')


def test_falta_pregunta_indica_archivo_e_id(tmp_path):
    msg = error(tmp_path, "- id: sin-pregunta\n  esperado: { contiene: a }\n")
    assert "malo.yaml" in msg and "sin-pregunta" in msg and "pregunta" in msg


def test_ids_repetidos_en_el_mismo_archivo(tmp_path):
    msg = error(tmp_path, caso_yaml(id="dup") + caso_yaml(id="dup"))
    assert "dup" in msg and "repetido" in msg and "malo.yaml" in msg


def test_ids_repetidos_entre_archivos(tmp_path):
    escribir(tmp_path, "a.yaml", caso_yaml(id="dup"))
    escribir(tmp_path, "b.yaml", caso_yaml(id="dup"))
    with pytest.raises(ValueError) as info:
        load_cases(tmp_path)
    msg = str(info.value)
    assert "dup" in msg and "repetido" in msg and "b.yaml" in msg and "a.yaml" in msg


def test_clave_desconocida_en_el_caso(tmp_path):
    msg = error(tmp_path, caso_yaml(repeticion="3"))  # errata: falta la "es"
    assert "claves desconocidas" in msg and "repeticion" in msg and "'c1'" in msg


def test_clave_desconocida_en_esperado(tmp_path):
    msg = error(tmp_path, caso_yaml(esperado="{ contiene: Lima, contienen: Cusco }"))
    assert "esperado" in msg and "contienen" in msg and "c1" in msg


def test_clave_repetida_en_el_mismo_mapa(tmp_path):
    msg = error(tmp_path, '- id: x\n  pregunta: "a"\n  pregunta: "b"\n  esperado: { contiene: a }\n')
    assert "repetida" in msg and "pregunta" in msg


@pytest.mark.parametrize("valor", ["0", "-2", "1.5", '"3"', "true", "null"])
def test_repeticiones_invalidas(tmp_path, valor):
    msg = error(tmp_path, caso_yaml(repeticiones=valor))
    assert "repeticiones" in msg and "c1" in msg


@pytest.mark.parametrize("valor", ["wrong", "ANSWER", '""', "3"])
def test_stop_reason_invalido(tmp_path, valor):
    msg = error(tmp_path, caso_yaml(esperado="{ stop_reason: %s }" % valor))
    assert "stop_reason" in msg and "c1" in msg


@pytest.mark.parametrize("razon", ["answer", "max_steps", "max_cost", "denied"])
def test_stop_reason_validos(tmp_path, razon):
    c = load_cases(escribir(tmp_path, "ok.yaml", caso_yaml(esperado="{ stop_reason: %s }" % razon)))[0]
    assert c.esperado.stop_reason == razon


@pytest.mark.parametrize("valor", ["0", "-1", "2.5", '"3"', "true", '"muchos"'])
def test_max_pasos_invalido(tmp_path, valor):
    msg = error(tmp_path, caso_yaml(esperado="{ contiene: a, max_pasos: %s }" % valor))
    assert "max_pasos" in msg and "c1" in msg


def test_contiene_con_valores_que_no_son_texto(tmp_path):
    # YAML 1.1: `no` es el booleano False; el mensaje debe sugerir las comillas
    msg = error(tmp_path, caso_yaml(esperado="{ contiene: [no] }"))
    assert "contiene" in msg and "comillas" in msg
    assert "contiene" in error(tmp_path, caso_yaml(esperado="{ contiene: 4500 }"), nombre="otro.yaml")
    assert "contiene" in error(tmp_path, caso_yaml(esperado="{ contiene: { a: b } }"), nombre="otro2.yaml")


def test_frase_vacia_no_se_acepta(tmp_path):
    assert "vacía" in error(tmp_path, caso_yaml(esperado='{ contiene: ["ok", "  "] }'))
    assert "no_contiene" in error(tmp_path, caso_yaml(esperado='{ no_contiene: "" }'), nombre="o.yaml")


def test_herramienta_debe_ser_texto_no_vacio(tmp_path):
    assert "herramienta" in error(tmp_path, caso_yaml(esperado="{ herramienta: 5 }"))
    assert "herramienta" in error(tmp_path, caso_yaml(esperado='{ herramienta: " " }'), nombre="o.yaml")


def test_esperado_sin_criterios_o_ausente(tmp_path):
    assert "ningún criterio" in error(tmp_path, caso_yaml(esperado="{ contiene: [], no_contiene: [] }"))
    sin_esperado = '- id: x\n  pregunta: "p"\n'
    assert "esperado" in error(tmp_path, sin_esperado, nombre="o.yaml")


def test_esperado_no_es_un_mapa(tmp_path):
    assert "esperado" in error(tmp_path, caso_yaml(esperado="[Lima]"))


def test_guion_debe_ser_lista(tmp_path):
    assert "guion" in error(tmp_path, caso_yaml(guion='"hola"'))


def test_raiz_no_es_lista(tmp_path):
    assert "LISTA" in error(tmp_path, 'id: x\npregunta: "p"\n')


def test_elemento_no_es_mapa(tmp_path):
    assert "#2" in error(tmp_path, caso_yaml() + '- "suelto"\n')


def test_archivo_vacio(tmp_path):
    assert "vacío" in error(tmp_path, "")


def test_yaml_invalido_indica_el_archivo(tmp_path):
    msg = error(tmp_path, "- id: [sin cerrar\n")
    assert "malo.yaml" in msg and "YAML inválido" in msg


def test_bytes_no_utf8(tmp_path):
    (tmp_path / "raro.yaml").write_bytes(b"- id: \xff\xfe\n")
    with pytest.raises(ValueError, match="raro.yaml"):
        load_cases(tmp_path / "raro.yaml")


def test_ruta_inexistente(tmp_path):
    with pytest.raises(ValueError, match="no existe"):
        load_cases(tmp_path / "nada.yaml")


def test_carpeta_sin_yaml(tmp_path):
    with pytest.raises(ValueError, match="no contiene"):
        load_cases(tmp_path)


def test_el_mensaje_de_error_de_una_carpeta_nombra_el_archivo_culpable(tmp_path):
    escribir(tmp_path, "a.yaml", caso_yaml(id="ok"))
    escribir(tmp_path, "b.yaml", caso_yaml(id="roto", repeticiones="0"))
    with pytest.raises(ValueError) as info:
        load_cases(tmp_path)
    assert "b.yaml" in str(info.value) and "roto" in str(info.value)


def test_yaml_con_etiquetas_python_no_se_ejecuta(tmp_path):
    msg = error(tmp_path, '- id: x\n  pregunta: !!python/object/apply:os.getcwd []\n  esperado: { contiene: a }\n')
    assert "YAML inválido" in msg
