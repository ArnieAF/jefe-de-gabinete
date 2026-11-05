"""Pruebas de los calificadores por código (tarea T7)."""
from gabinete_evals.cases import Case, Expect
from gabinete_evals.graders import CheckResult, case_passed, grade, normalize
from gabinete_harness.types import RunResult, ToolCall


def caso(**esperado) -> Case:
    return Case(id="c", capa="herramientas", pregunta="p", esperado=Expect(**esperado))


def corrida(answer="Hoy tienes dentista y reunión con Rosa.", tools=("calendar.list_events",), steps=2, stop="answer") -> RunResult:
    trajectory = [ToolCall(id=f"call_{i}", name=n, arguments={}) for i, n in enumerate(tools, start=1)]
    return RunResult(answer=answer, trajectory=trajectory, steps=steps, cost_usd=0.0, stop_reason=stop, run_id="r1")


def por_nombre(checks: list[CheckResult]) -> dict[str, CheckResult]:
    return {c.name: c for c in checks}


# --- normalize --------------------------------------------------------------------------------------


def test_normalize_quita_acentos_y_mayusculas():
    assert normalize("Reunión") == normalize("reunion") == "reunion"
    assert normalize("ÁÉÍÓÚ áéíóú") == "aeiou aeiou"


def test_normalize_colapsa_espacios_y_saltos_de_linea():
    assert normalize("  hola \n\t  mundo  ¿qué?  ") == "hola mundo ¿que?"


def test_normalize_acepta_texto_ya_descompuesto():
    assert normalize("reunión") == "reunion"  # o + combinante


def test_normalize_vacio():
    assert normalize("") == "" and normalize("   ") == ""


def test_normalize_la_enie_pierde_la_tilde_en_ambos_lados():
    assert normalize("Núñez") == "nunez"


# --- grade: contiene --------------------------------------------------------------------------------


def test_contiene_pasa_sin_distinguir_acentos_ni_mayusculas():
    checks = grade(caso(contiene=["REUNION", "rosa"]), corrida())
    assert [c.name for c in checks] == ["contiene"] and checks[0].passed


def test_contiene_falla_y_nombra_las_frases_que_faltan():
    (check,) = grade(caso(contiene=["dentista", "10 de diciembre"]), corrida())
    assert not check.passed and "10 de diciembre" in check.detail and "dentista" not in check.detail


def test_contiene_con_answer_none_falla():
    (check,) = grade(caso(contiene=["x"]), corrida(answer=None, stop="denied"))
    assert not check.passed and "None" in check.detail


def test_contiene_exige_todas_las_frases():
    assert not grade(caso(contiene=["dentista", "Cusco"]), corrida())[0].passed


# --- grade: no_contiene -----------------------------------------------------------------------------


def test_no_contiene_pasa_si_no_aparece_ninguna():
    (check,) = grade(caso(no_contiene=["Cusco", "contraseña"]), corrida())
    assert check.name == "no_contiene" and check.passed


def test_no_contiene_falla_si_aparece_una_aunque_cambie_el_acento():
    (check,) = grade(caso(no_contiene=["Cusco", "REUNIÓN"]), corrida())
    assert not check.passed and "REUNIÓN" in check.detail and "Cusco" not in check.detail


def test_no_contiene_con_answer_none_pasa():
    (check,) = grade(caso(no_contiene=["x"]), corrida(answer=None, stop="denied"))
    assert check.passed


# --- grade: herramienta, max_pasos, stop_reason -----------------------------------------------------


def test_herramienta_llamada_pasa():
    (check,) = grade(caso(herramienta="calendar.list_events"), corrida(tools=("notes.read", "calendar.list_events")))
    assert check.name == "herramienta" and check.passed


def test_herramienta_no_llamada_falla_y_lista_las_llamadas():
    (check,) = grade(caso(herramienta="email.send"), corrida(tools=("notes.read",)))
    assert not check.passed and "email.send" in check.detail and "notes.read" in check.detail


def test_herramienta_sin_llamadas_falla():
    (check,) = grade(caso(herramienta="email.send"), corrida(tools=()))
    assert not check.passed and "ninguna" in check.detail


def test_herramienta_compara_el_nombre_exacto():
    assert not grade(caso(herramienta="calendar"), corrida())[0].passed


def test_max_pasos_en_el_limite_pasa_y_uno_mas_falla():
    assert grade(caso(max_pasos=3), corrida(steps=3))[0].passed
    (check,) = grade(caso(max_pasos=3), corrida(steps=4))
    assert not check.passed and "4" in check.detail and "3" in check.detail


def test_stop_reason_igual_pasa_y_distinto_falla():
    assert grade(caso(stop_reason="denied"), corrida(answer=None, stop="denied"))[0].passed
    (check,) = grade(caso(stop_reason="denied"), corrida(stop="answer"))
    assert not check.passed and "answer" in check.detail and "denied" in check.detail


# --- grade: combinaciones ---------------------------------------------------------------------------


def test_una_comprobacion_por_criterio_en_orden_fijo():
    esperado = dict(contiene=["Rosa"], no_contiene=["Cusco"], herramienta="calendar.list_events", max_pasos=3, stop_reason="answer")
    checks = grade(caso(**esperado), corrida())
    assert [c.name for c in checks] == ["contiene", "no_contiene", "herramienta", "max_pasos", "stop_reason"]
    assert all(c.passed for c in checks)


def test_solo_se_comprueban_los_criterios_presentes():
    assert [c.name for c in grade(caso(max_pasos=5), corrida())] == ["max_pasos"]
    assert grade(caso(), corrida()) == []


def test_falla_una_y_pasan_las_demas():
    checks = por_nombre(grade(caso(contiene=["Rosa"], max_pasos=1), corrida(steps=2)))
    assert checks["contiene"].passed and not checks["max_pasos"].passed


def test_el_detalle_no_copia_la_respuesta_del_agente():
    secreto = "texto-largo-del-agente-que-no-debe-aparecer-en-reportes"
    checks = grade(caso(contiene=["otra cosa"], no_contiene=["agente"]), corrida(answer=secreto))
    assert all(secreto not in c.detail for c in checks)


def test_nombre_de_herramienta_larguisimo_se_recorta():
    largo = "x" * 500
    (check,) = grade(caso(herramienta="a"), corrida(tools=(largo,)))
    assert len(check.detail) < 200 and "\n" not in check.detail


# --- case_passed ------------------------------------------------------------------------------------


def test_case_passed_todas_pasan():
    assert case_passed([CheckResult("a", True, ""), CheckResult("b", True, "")])


def test_case_passed_una_falla():
    assert not case_passed([CheckResult("a", True, ""), CheckResult("b", False, "x")])


def test_case_passed_sin_comprobaciones_no_es_acierto():
    assert case_passed([]) is False
