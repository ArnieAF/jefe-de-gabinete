"""Pruebas de los tipos del contrato (tarea T1)."""
import pytest

from gabinete_harness.types import (
    STOP_REASONS,
    LLMProvider,
    LLMResponse,
    Message,
    RunResult,
    Tool,
    ToolCall,
    ToolSpec,
    Usage,
    allow_all,
    deny_all,
)


def test_defaults_de_los_tipos():
    msg = Message(role="user", content="hola")
    assert msg.tool_calls == [] and msg.tool_call_id is None
    resp = LLMResponse(text="ok")
    assert resp.tool_calls == [] and resp.usage == Usage()
    assert Usage().cost_usd == 0.0


def test_los_defaults_mutables_no_se_comparten():
    a, b = Message(role="user"), Message(role="user")
    a.tool_calls.append(ToolCall(id="1", name="x", arguments={}))
    assert b.tool_calls == []


def test_rol_invalido_falla_con_mensaje_claro():
    with pytest.raises(ValueError, match="rol inválido"):
        Message(role="robot")


def test_stop_reason_invalido_falla():
    with pytest.raises(ValueError, match="stop_reason inválido"):
        RunResult(answer=None, trajectory=[], steps=0, cost_usd=0.0, stop_reason="otra", run_id="r1")
    for razon in STOP_REASONS:
        assert RunResult(answer=None, trajectory=[], steps=0, cost_usd=0.0, stop_reason=razon, run_id="r1")


def test_tool_expone_su_nombre_y_no_pide_aprobacion_por_defecto():
    spec = ToolSpec(name="calendar.list_events", description="Lista eventos", schema={"type": "object"})
    tool = Tool(spec=spec, fn=lambda args: "[]")
    assert tool.name == "calendar.list_events"
    assert tool.requires_approval is False


def test_un_objeto_con_name_y_chat_cumple_el_protocolo_llmprovider():
    class Falso:
        name = "falso"

        def chat(self, messages, tools=None, *, max_tokens=1024):
            return LLMResponse(text="hola")

    assert isinstance(Falso(), LLMProvider)
    assert not isinstance(object(), LLMProvider)


def test_aprobacion_por_defecto_deniega_y_allow_all_aprueba():
    llamada = ToolCall(id="c1", name="email.send", arguments={})
    assert deny_all(llamada) is False
    assert allow_all(llamada) is True
