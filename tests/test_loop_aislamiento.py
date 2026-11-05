"""El proveedor no puede alterar, después de devolverlas, las llamadas que el bucle registra, aprueba y califica
(hallazgo seg-3 / cor-1 de la auditoría de F1)."""
import json

from gabinete_harness.loop import run
from gabinete_harness.types import LLMResponse, Tool, ToolCall, ToolSpec


class ProveedorMutante:
    """Conserva la referencia a lo que devolvió y, en la llamada siguiente, intenta reescribirlo."""

    name = "mutante"

    def __init__(self) -> None:
        self.llamadas = 0
        self.primera: LLMResponse | None = None

    def chat(self, messages, tools=None, *, max_tokens=1024):
        self.llamadas += 1
        if self.llamadas == 1:
            self.primera = LLMResponse(
                tool_calls=[ToolCall(id="c1", name="lee", arguments={"x": 1})],
            )
            return self.primera
        assert self.primera is not None
        self.primera.tool_calls[0].name = "email.send"
        self.primera.tool_calls[0].arguments["x"] = "ALTERADO"
        return LLMResponse(text="listo")


def _herramienta_lee(ejecutadas: list) -> Tool:
    def fn(args: dict) -> str:
        ejecutadas.append(dict(args))
        return "ok"

    return Tool(spec=ToolSpec(name="lee", description="lee", schema={"type": "object"}), fn=fn)


def test_la_trayectoria_calificada_no_cambia_aunque_el_proveedor_mute_lo_que_devolvio(tmp_path):
    ejecutadas: list = []
    resultado = run("hola", "s1", provider=ProveedorMutante(), tools=[_herramienta_lee(ejecutadas)], log_dir=tmp_path)
    assert resultado.stop_reason == "answer"
    assert [(c.name, c.arguments) for c in resultado.trajectory] == [("lee", {"x": 1})]
    assert ejecutadas == [{"x": 1}]  # lo que se ejecutó es lo que se pidió, no lo que se mutó después


def test_el_registro_y_la_trayectoria_coinciden(tmp_path):
    resultado = run("hola", "s2", provider=ProveedorMutante(), tools=[_herramienta_lee([])], log_dir=tmp_path)
    eventos = [json.loads(linea) for linea in next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()]
    pedido = next(e for e in eventos if e["type"] == "tool_call")
    assert (pedido["name"], pedido["arguments"]) == (resultado.trajectory[0].name, resultado.trajectory[0].arguments)


def test_el_proveedor_recibe_en_la_segunda_llamada_la_llamada_original_en_el_historial(tmp_path):
    vistos: list = []

    class Espia(ProveedorMutante):
        def chat(self, messages, tools=None, *, max_tokens=1024):
            vistos.append([(c.name, dict(c.arguments)) for m in messages for c in m.tool_calls])
            return super().chat(messages, tools, max_tokens=max_tokens)

    run("hola", "s3", provider=Espia(), tools=[_herramienta_lee([])], log_dir=tmp_path)
    assert vistos[1] == [("lee", {"x": 1})]
