"""Pruebas del ScriptedProvider (tarea T2)."""
import inspect

import pytest

from gabinete_harness.providers.scripted import RecordedCall, ScriptedProvider, ScriptExhaustedError
from gabinete_harness.types import LLMProvider, LLMResponse, Message, ToolCall, ToolSpec, Usage


def _mensajes() -> list[Message]:
    return [Message(role="system", content="eres un asistente"), Message(role="user", content="hola")]


def _spec(nombre: str) -> ToolSpec:
    return ToolSpec(name=nombre, description="d", schema={"type": "object"})


# ---------------------------------------------------------------- orden y agotamiento

def test_devuelve_las_respuestas_en_orden():
    proveedor = ScriptedProvider(
        [
            {"tool_calls": [{"name": "calendar.list_events", "arguments": {"date": "2026-11-05"}}]},
            {"text": "Tienes dentista."},
            {"text": "Fin."},
        ]
    )
    r1, r2, r3 = (proveedor.chat(_mensajes()) for _ in range(3))
    assert r1.text is None and [c.name for c in r1.tool_calls] == ["calendar.list_events"]
    assert r1.tool_calls[0].arguments == {"date": "2026-11-05"}
    assert r2.text == "Tienes dentista." and r2.tool_calls == []
    assert r3.text == "Fin."
    assert proveedor.remaining == 0


def test_un_llmresponse_se_devuelve_tal_cual():
    respuesta = LLMResponse(text="directo", usage=Usage(input_tokens=3, output_tokens=4, cost_usd=0.5))
    proveedor = ScriptedProvider([respuesta])
    assert proveedor.chat(_mensajes()) is respuesta


def test_se_puede_mezclar_llmresponse_y_dicts_y_usar_una_tupla():
    respuesta = LLMResponse(text="uno")
    proveedor = ScriptedProvider((respuesta, {"text": "dos"}))
    assert proveedor.chat(_mensajes()) is respuesta
    assert proveedor.chat(_mensajes()).text == "dos"


def test_guion_agotado_lanza_error_claro_con_las_cuentas():
    proveedor = ScriptedProvider([{"text": "a"}, {"text": "b"}])
    proveedor.chat(_mensajes())
    proveedor.chat(_mensajes())
    with pytest.raises(ScriptExhaustedError) as info:
        proveedor.chat(_mensajes())
    mensaje = str(info.value)
    assert "2 respuesta(s)" in mensaje and "3 llamada(s)" in mensaje


def test_guion_agotado_sigue_fallando_en_llamadas_posteriores():
    proveedor = ScriptedProvider([{"text": "a"}])
    proveedor.chat(_mensajes())
    for esperadas in (2, 3):
        with pytest.raises(ScriptExhaustedError, match=f"{esperadas} llamada"):
            proveedor.chat(_mensajes())


def test_guion_vacio_es_valido_y_falla_en_la_primera_llamada():
    proveedor = ScriptedProvider([])
    with pytest.raises(ScriptExhaustedError, match=r"0 respuesta\(s\).*1 llamada"):
        proveedor.chat(_mensajes())


def test_script_exhausted_error_es_una_excepcion_normal():
    assert issubclass(ScriptExhaustedError, Exception)


# ---------------------------------------------------------------- ids de llamadas

def test_los_ids_se_generan_en_secuencia_y_no_se_reinician_entre_respuestas():
    proveedor = ScriptedProvider(
        [
            {"tool_calls": [{"name": "a"}, {"name": "b"}]},
            {"tool_calls": [{"name": "c"}]},
        ]
    )
    primera, segunda = proveedor.chat(_mensajes()), proveedor.chat(_mensajes())
    assert [c.id for c in primera.tool_calls] == ["call_1", "call_2"]
    assert [c.id for c in segunda.tool_calls] == ["call_3"]


def test_cada_instancia_cuenta_sus_propios_ids():
    guion = [{"tool_calls": [{"name": "a"}]}]
    uno, otro = ScriptedProvider(guion), ScriptedProvider(guion)
    assert uno.chat(_mensajes()).tool_calls[0].id == "call_1"
    assert otro.chat(_mensajes()).tool_calls[0].id == "call_1"


def test_los_ids_explicitos_se_respetan_y_no_gastan_el_contador():
    proveedor = ScriptedProvider(
        [{"tool_calls": [{"name": "a", "id": "abc"}, {"name": "b"}, {"name": "c", "id": "xyz"}, {"name": "d"}]}]
    )
    ids = [c.id for c in proveedor.chat(_mensajes()).tool_calls]
    assert ids == ["abc", "call_1", "xyz", "call_2"]


def test_un_id_generado_no_choca_con_uno_explicito_del_guion():
    proveedor = ScriptedProvider(
        [
            {"tool_calls": [{"name": "a"}]},
            {"tool_calls": [{"name": "b", "id": "call_1"}, {"name": "c"}]},
        ]
    )
    primera, segunda = proveedor.chat(_mensajes()), proveedor.chat(_mensajes())
    assert primera.tool_calls[0].id == "call_2"
    assert [c.id for c in segunda.tool_calls] == ["call_1", "call_3"]


def test_un_id_generado_no_choca_con_los_ids_de_un_llmresponse():
    respuesta = LLMResponse(tool_calls=[ToolCall(id="call_1", name="x", arguments={})])
    proveedor = ScriptedProvider([respuesta, {"tool_calls": [{"name": "y"}]}])
    proveedor.chat(_mensajes())
    assert proveedor.chat(_mensajes()).tool_calls[0].id == "call_2"


def test_dos_ids_explicitos_iguales_fallan_indicando_donde_se_uso_antes():
    guion = [{"tool_calls": [{"name": "a", "id": "x"}]}, {"tool_calls": [{"name": "b", "id": "x"}]}]
    with pytest.raises(ValueError, match=r"guion\[1\].*'x'.*guion\[0\]\.tool_calls\[0\]"):
        ScriptedProvider(guion)


def test_arguments_por_defecto_es_un_dict_vacio_y_no_se_comparte():
    proveedor = ScriptedProvider([{"tool_calls": [{"name": "a"}, {"name": "b"}]}])
    a, b = proveedor.chat(_mensajes()).tool_calls
    assert a.arguments == {} and b.arguments == {}
    a.arguments["x"] = 1
    assert b.arguments == {}


def test_cambiar_el_guion_original_despues_de_construir_no_afecta_al_proveedor():
    argumentos = {"date": "2026-11-05"}
    guion = [{"tool_calls": [{"name": "a", "arguments": argumentos}]}]
    proveedor = ScriptedProvider(guion)
    argumentos["date"] = "otra"
    assert proveedor.chat(_mensajes()).tool_calls[0].arguments == {"date": "2026-11-05"}
    assert "id" not in guion[0]["tool_calls"][0]  # el guion del llamador no se modifica


# ---------------------------------------------------------------- text / tool_calls

def test_una_respuesta_con_tool_calls_y_text_none_es_valida():
    respuesta = ScriptedProvider([{"text": None, "tool_calls": [{"name": "a"}]}]).chat(_mensajes())
    assert respuesta.text is None and len(respuesta.tool_calls) == 1


def test_una_respuesta_puede_traer_texto_y_llamadas_a_la_vez():
    respuesta = ScriptedProvider([{"text": "voy a buscar", "tool_calls": [{"name": "a"}]}]).chat(_mensajes())
    assert respuesta.text == "voy a buscar" and respuesta.tool_calls[0].name == "a"


def test_un_texto_vacio_explicito_es_valido():
    assert ScriptedProvider([{"text": ""}]).chat(_mensajes()).text == ""


# ---------------------------------------------------------------- usage

def test_usage_ausente_es_cero():
    assert ScriptedProvider([{"text": "x"}]).chat(_mensajes()).usage == Usage()


def test_usage_dado_se_usa():
    proveedor = ScriptedProvider(
        [{"text": "x", "usage": {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.25}}]
    )
    assert proveedor.chat(_mensajes()).usage == Usage(input_tokens=10, output_tokens=5, cost_usd=0.25)


def test_usage_parcial_completa_con_ceros_y_el_costo_entero_pasa_a_float():
    usage = ScriptedProvider([{"text": "x", "usage": {"cost_usd": 2}}]).chat(_mensajes()).usage
    assert usage == Usage(input_tokens=0, output_tokens=0, cost_usd=2.0)
    assert isinstance(usage.cost_usd, float)


def test_usage_none_equivale_a_ausente():
    assert ScriptedProvider([{"text": "x", "usage": None}]).chat(_mensajes()).usage == Usage()


@pytest.mark.parametrize(
    "usage, fragmento",
    [
        ("caro", "`usage` debe ser un dict"),
        ({"tokens": 3}, "claves desconocidas"),
        ({"input_tokens": -1}, "input_tokens"),
        ({"output_tokens": 1.5}, "output_tokens"),
        ({"input_tokens": True}, "input_tokens"),
        ({"cost_usd": -0.1}, "cost_usd"),
        ({"cost_usd": float("nan")}, "cost_usd"),
        ({"cost_usd": float("inf")}, "cost_usd"),
        ({"cost_usd": "1"}, "cost_usd"),
        ({"cost_usd": True}, "cost_usd"),
    ],
)
def test_usage_invalido_falla_al_construir(usage, fragmento):
    with pytest.raises(ValueError, match=r"guion\[0\]") as info:
        ScriptedProvider([{"text": "x", "usage": usage}])
    assert fragmento in str(info.value)


# ---------------------------------------------------------------- validación del guion

def test_dict_vacio_falla_indicando_el_indice():
    with pytest.raises(ValueError, match=r"guion\[2\].*vacía"):
        ScriptedProvider([{"text": "a"}, {"text": "b"}, {}])


@pytest.mark.parametrize(
    "elemento",
    [
        {"usage": {"input_tokens": 1}},
        {"text": None},
        {"tool_calls": []},
        {"text": None, "tool_calls": []},
    ],
)
def test_respuestas_sin_texto_ni_llamadas_son_vacias(elemento):
    with pytest.raises(ValueError, match=r"guion\[0\].*vacía"):
        ScriptedProvider([elemento])


def test_claves_desconocidas_fallan_nombrandolas_y_el_indice():
    with pytest.raises(ValueError, match=r"guion\[1\]") as info:
        ScriptedProvider([{"text": "a"}, {"text": "b", "texto": "c", "tools": []}])
    mensaje = str(info.value)
    assert "claves desconocidas" in mensaje and "'texto'" in mensaje and "'tools'" in mensaje


def test_llamada_sin_name_falla_con_indice_de_respuesta_y_de_llamada():
    with pytest.raises(ValueError, match=r"guion\[1\].*tool_calls\[1\].*name"):
        ScriptedProvider([{"text": "a"}, {"tool_calls": [{"name": "ok"}, {"arguments": {}}]}])


@pytest.mark.parametrize("nombre", ["", "   ", None, 5, ["x"]])
def test_name_debe_ser_un_texto_no_vacio(nombre):
    with pytest.raises(ValueError, match=r"guion\[0\].*name"):
        ScriptedProvider([{"tool_calls": [{"name": nombre}]}])


@pytest.mark.parametrize("argumentos", ["{}", [], None, 3, ("a", 1)])
def test_arguments_que_no_es_dict_falla(argumentos):
    with pytest.raises(ValueError, match=r"guion\[0\].*arguments debe ser un dict"):
        ScriptedProvider([{"tool_calls": [{"name": "a", "arguments": argumentos}]}])


@pytest.mark.parametrize("identificador", ["", "  ", 7, None])
def test_id_explicito_invalido_falla(identificador):
    with pytest.raises(ValueError, match=r"guion\[0\].*\.id debe ser"):
        ScriptedProvider([{"tool_calls": [{"name": "a", "id": identificador}]}])


def test_una_clave_desconocida_dentro_de_una_llamada_falla():
    with pytest.raises(ValueError, match=r"guion\[0\].*tool_calls\[0\].*'args'"):
        ScriptedProvider([{"tool_calls": [{"name": "a", "args": {}}]}])


def test_llamada_que_no_es_dict_falla():
    with pytest.raises(ValueError, match=r"guion\[0\].*tool_calls\[0\].*ToolCall"):
        ScriptedProvider([{"tool_calls": [ToolCall(id="1", name="a", arguments={})]}])


@pytest.mark.parametrize("llamadas", ["a", {"name": "a"}, 3])
def test_tool_calls_que_no_es_lista_falla(llamadas):
    with pytest.raises(ValueError, match=r"guion\[0\].*`tool_calls` debe ser una lista"):
        ScriptedProvider([{"tool_calls": llamadas}])


@pytest.mark.parametrize("texto", [5, ["a"], b"a"])
def test_text_con_tipo_invalido_falla(texto):
    with pytest.raises(ValueError, match=r"guion\[0\].*`text` debe ser un texto"):
        ScriptedProvider([{"text": texto}])


@pytest.mark.parametrize("elemento", ["hola", 3, None, ["text", "x"], ToolCall(id="1", name="a", arguments={})])
def test_elemento_que_no_es_dict_ni_llmresponse_falla(elemento):
    with pytest.raises(ValueError, match=r"guion\[1\].*dict o un LLMResponse"):
        ScriptedProvider([{"text": "a"}, elemento])


@pytest.mark.parametrize("guion", ["texto", b"bytes", {"text": "a"}, 5, None, {"a", "b"}])
def test_el_guion_debe_ser_una_secuencia(guion):
    with pytest.raises(ValueError, match="debe ser una lista de respuestas"):
        ScriptedProvider(guion)


def test_la_validacion_ocurre_al_construir_no_al_llamar():
    # El error está en el elemento 1, pero se detecta antes de la primera llamada a chat().
    with pytest.raises(ValueError, match=r"guion\[1\]"):
        ScriptedProvider([{"text": "bien"}, {"tool_calls": [{"arguments": {}}]}])


# ---------------------------------------------------------------- registro `calls`

def test_calls_guarda_un_registro_por_llamada_con_mensajes_herramientas_y_max_tokens():
    proveedor = ScriptedProvider([{"text": "a"}, {"text": "b"}])
    proveedor.chat(_mensajes(), [_spec("calendar.list_events"), _spec("notes.read")], max_tokens=256)
    proveedor.chat(_mensajes()[:1])
    assert len(proveedor.calls) == 2
    primera, segunda = proveedor.calls
    assert isinstance(primera, RecordedCall)
    assert primera.messages == _mensajes() and primera.max_tokens == 256
    assert primera.tool_names == ["calendar.list_events", "notes.read"]
    assert segunda.messages == _mensajes()[:1] and segunda.max_tokens == 1024
    assert segunda.tool_names == []


def test_calls_registra_tools_none_y_lista_vacia_como_sin_herramientas():
    proveedor = ScriptedProvider([{"text": "a"}, {"text": "b"}])
    proveedor.chat(_mensajes(), None)
    proveedor.chat(_mensajes(), [])
    assert [c.tool_names for c in proveedor.calls] == [[], []]


def test_calls_es_una_copia_mutar_los_mensajes_despues_no_altera_el_registro():
    proveedor = ScriptedProvider([{"text": "a"}])
    mensajes = _mensajes()
    mensajes.append(Message(role="assistant", content="x", tool_calls=[ToolCall(id="c1", name="t", arguments={"k": 1})]))
    proveedor.chat(mensajes)
    # Lo que haría el bucle: añadir mensajes a la misma lista y tocar los objetos ya enviados.
    mensajes.append(Message(role="tool", content="resultado", tool_call_id="c1"))
    mensajes[0].content = "cambiado"
    mensajes[2].tool_calls[0].arguments["k"] = 99
    mensajes[2].tool_calls.append(ToolCall(id="c2", name="u", arguments={}))
    registro = proveedor.calls[0].messages
    assert len(registro) == 3
    assert registro[0].content == "eres un asistente"
    assert registro[2].tool_calls == [ToolCall(id="c1", name="t", arguments={"k": 1})]


def test_calls_registra_tambien_la_llamada_que_agota_el_guion():
    proveedor = ScriptedProvider([{"text": "a"}])
    proveedor.chat(_mensajes())
    with pytest.raises(ScriptExhaustedError):
        proveedor.chat([Message(role="user", content="otra")])
    assert len(proveedor.calls) == 2
    assert proveedor.calls[1].messages[0].content == "otra"


def test_cada_instancia_tiene_su_propio_registro():
    uno, otro = ScriptedProvider([{"text": "a"}]), ScriptedProvider([{"text": "a"}])
    uno.chat(_mensajes())
    assert len(uno.calls) == 1 and otro.calls == []


# ---------------------------------------------------------------- protocolo

def test_cumple_el_protocolo_llmprovider_y_se_llama_scripted():
    proveedor = ScriptedProvider([{"text": "a"}])
    assert isinstance(proveedor, LLMProvider)
    assert proveedor.name == "scripted" == ScriptedProvider.name


def test_la_firma_de_chat_coincide_con_la_del_protocolo():
    esperada = inspect.signature(LLMProvider.chat).parameters
    real = inspect.signature(ScriptedProvider.chat).parameters
    assert list(real) == list(esperada)
    for nombre, parametro in esperada.items():
        assert real[nombre].kind == parametro.kind, nombre
        assert real[nombre].default == parametro.default, nombre
    assert real["max_tokens"].kind is inspect.Parameter.KEYWORD_ONLY
