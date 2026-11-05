"""Pruebas de la limpieza de secretos (hallazgo de la auditoría de F1) y de su cableado en registros, reportes y errores."""
import json
from pathlib import Path

import pytest

from gabinete_evals.cases import Case, Expect
from gabinete_evals.cli import render_summary
from gabinete_evals.report import write_report
from gabinete_evals.suite import run_suite
from gabinete_harness.loop import run
from gabinete_harness.providers.scripted import ScriptedProvider
from gabinete_harness.redact import REDACTED, scrub
from gabinete_harness.types import LLMResponse, Tool, ToolCall, ToolSpec

CLAVE_GEMINI = "AIzaSyFAKE0000000000000000000000000000X"  # inventada, con la forma de una clave de Google
URL_CON_CLAVE = f"https://generativelanguage.googleapis.com/v1beta/models/m:generateContent?key={CLAVE_GEMINI}"
ERROR_HTTP = f"400 Client Error: Bad Request for url: {URL_CON_CLAVE}"


def test_limpia_la_clave_en_la_url_y_la_forma_reconocible():
    limpio = scrub(ERROR_HTTP)
    assert CLAVE_GEMINI not in limpio and "key=" in limpio and REDACTED in limpio
    assert scrub(f"clave suelta {CLAVE_GEMINI} fin").count(REDACTED) == 1


@pytest.mark.parametrize(
    "texto, secreto",
    [
        ("GET /x?api_key=abc123secretvalue&otro=1", "abc123secretvalue"),
        ("GET /x?a=1&token=ghp_abcdefghijklmnopqrstuvwxyz0123", "ghp_abcdefghijklmnopqrstuvwxyz0123"),
        ("Authorization: Bearer abcdef0123456789.xyz-token", "abcdef0123456789.xyz-token"),
        ("sk-abcdefghijklmnop0123456789", "sk-abcdefghijklmnop0123456789"),
        ("xoxb-1234567890-abcdefghij", "xoxb-1234567890-abcdefghij"),
    ],
)
def test_otras_formas_de_secreto(texto, secreto):
    limpio = scrub(texto)
    assert secreto not in limpio and REDACTED in limpio


def test_limpia_el_valor_literal_de_las_variables_de_entorno_que_parecen_secretos(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "valor-secreto-sin-forma-conocida")
    monkeypatch.setenv("NOMBRE_NORMAL", "valor-que-no-es-secreto")
    limpio = scrub("fallo con valor-secreto-sin-forma-conocida y con valor-que-no-es-secreto")
    assert "valor-secreto-sin-forma-conocida" not in limpio
    assert "valor-que-no-es-secreto" in limpio  # solo se limpian las variables con nombre de secreto


def test_las_variables_cortas_no_se_limpian_para_no_destruir_texto_normal(monkeypatch):
    monkeypatch.setenv("ALGO_TOKEN", "abc")
    assert scrub("el abc de la vida") == "el abc de la vida"


@pytest.mark.parametrize("texto", ["", "Hoy tienes la cita con el dentista a las 11:30.", "key sin igual y token: nada", "clave = valor"])
def test_no_toca_el_texto_normal(texto):
    assert scrub(texto) == texto


class ProveedorQueFalla:
    """Imita a un adaptador HTTP cuyo error trae la URL completa, con la clave dentro."""

    name = "gemini"

    def chat(self, messages, tools=None, *, max_tokens=1024):
        raise RuntimeError(ERROR_HTTP)


def _caso() -> Case:
    return Case(id="c1", capa="herramientas", pregunta="¿Qué tengo hoy?", esperado=Expect(contiene=["x"]))


def test_la_clave_no_llega_al_registro_ni_al_reporte_ni_a_la_pantalla(tmp_path):
    logs, out = tmp_path / "logs", tmp_path / "out"

    def execute(caso):
        return run(caso.pregunta, "s1", provider=ProveedorQueFalla(), tools=[], log_dir=logs)

    with pytest.raises(RuntimeError):  # run() re-lanza el error del proveedor, pero ya limpio en el registro
        run("hola", "s0", provider=ProveedorQueFalla(), tools=[], log_dir=logs)
    suite = run_suite([_caso()], execute)
    json_path, md_path = write_report(suite, out, "r1")

    registros = "".join(p.read_text(encoding="utf-8") for p in logs.glob("*.jsonl"))
    assert "run_error" in registros and CLAVE_GEMINI not in registros and REDACTED in registros
    assert CLAVE_GEMINI not in json_path.read_text(encoding="utf-8")
    assert CLAVE_GEMINI not in md_path.read_text(encoding="utf-8")
    resumen = render_summary(suite, run_id="r1", provider="gemini", min_rate=1.0, paths=(json_path, md_path))
    assert CLAVE_GEMINI not in resumen and "excepción" in resumen


def test_el_error_de_una_herramienta_vuelve_limpio_al_modelo_y_al_registro(tmp_path):
    def falla(_args: dict) -> str:
        raise RuntimeError(ERROR_HTTP)

    herramienta = Tool(spec=ToolSpec(name="x.y", description="falla", schema={"type": "object"}), fn=falla)
    proveedor = ScriptedProvider([{"tool_calls": [{"name": "x.y"}]}, {"text": "listo"}])
    resultado = run("hola", "s2", provider=proveedor, tools=[herramienta], log_dir=tmp_path)
    assert resultado.stop_reason == "answer"
    visto_por_el_modelo = proveedor.calls[1].messages[-1].content
    assert visto_por_el_modelo.startswith("ERROR: RuntimeError") and CLAVE_GEMINI not in visto_por_el_modelo
    registro = next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8")
    assert CLAVE_GEMINI not in registro


def test_un_texto_con_clave_en_una_nota_leida_tampoco_queda_en_el_registro(tmp_path):
    herramienta = Tool(
        spec=ToolSpec(name="notas.leer", description="lee", schema={"type": "object"}),
        fn=lambda _a: json.dumps({"content": f"mi clave es {CLAVE_GEMINI}"}),
    )
    proveedor = ScriptedProvider([{"tool_calls": [{"name": "notas.leer"}]}, {"text": "ok"}])
    run("hola", "s3", provider=proveedor, tools=[herramienta], log_dir=tmp_path)
    registro = next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8")
    assert CLAVE_GEMINI not in registro
