"""Pruebas del runner de la suite (tarea T7): 2 casos de juguete, repeticiones, excepciones y `repetitions`."""
import pytest

from gabinete_evals.cases import Case, Expect
from gabinete_evals.suite import CaseOutcome, SuiteResult, run_suite
from gabinete_harness.types import RunResult, ToolCall


def resultado(answer="Hoy tienes dentista con Rosa", tools=("calendar.list_events",), steps=2, stop="answer") -> RunResult:
    trajectory = [ToolCall(id=f"call_{i}", name=n, arguments={}) for i, n in enumerate(tools, start=1)]
    return RunResult(answer=answer, trajectory=trajectory, steps=steps, cost_usd=0.0, stop_reason=stop, run_id="r")


def caso(id="a", capa="herramientas", repeticiones=1, **esperado) -> Case:
    esperado = esperado or {"contiene": ["dentista"]}
    return Case(id=id, capa=capa, pregunta="p", esperado=Expect(**esperado), repeticiones=repeticiones)


def test_dos_casos_de_juguete_uno_pasa_y_otro_falla():
    cases = [caso("pasa", contiene=["dentista"]), caso("falla", capa="rag", contiene=["Cusco"])]
    suite = run_suite(cases, lambda c: resultado())
    assert isinstance(suite, SuiteResult)
    assert [o.case_id for o in suite.outcomes] == ["pasa", "falla"]
    pasa, falla = suite.outcomes
    assert isinstance(pasa, CaseOutcome)
    assert (pasa.capa, pasa.runs, pasa.passes, pasa.rate, pasa.failures) == ("herramientas", 1, 1, 1.0, [])
    assert (falla.capa, falla.runs, falla.passes, falla.rate) == ("rag", 1, 0, 0.0)
    assert len(falla.failures) == 1 and "Cusco" in falla.failures[0] and falla.failures[0].startswith("contiene:")
    assert (suite.total_runs, suite.total_passes, suite.rate) == (2, 1, 0.5)


def test_cada_caso_se_repite_segun_sus_repeticiones():
    llamadas: list[str] = []

    def execute(c: Case) -> RunResult:
        llamadas.append(c.id)
        return resultado()

    suite = run_suite([caso("a", repeticiones=3), caso("b", repeticiones=2)], execute)
    assert llamadas == ["a", "a", "a", "b", "b"]  # orden determinista
    assert [(o.runs, o.passes) for o in suite.outcomes] == [(3, 3), (2, 2)]
    assert suite.total_runs == 5


def test_tasa_parcial_con_repeticiones():
    respuestas = iter(["dentista", "nada", "dentista", "dentista"])
    suite = run_suite([caso("a", repeticiones=4)], lambda c: resultado(answer=next(respuestas)))
    (o,) = suite.outcomes
    assert (o.runs, o.passes, o.rate) == (4, 3, 0.75)
    assert suite.rate == 0.75


def test_failures_no_repite_el_mismo_texto():
    suite = run_suite([caso("a", repeticiones=5, contiene=["Cusco"])], lambda c: resultado())
    (o,) = suite.outcomes
    assert o.passes == 0 and len(o.failures) == 1


def test_failures_junta_textos_distintos_en_orden():
    respuestas = iter(["nada", "dentista Cusco"])
    cases = [caso("a", repeticiones=2, contiene=["dentista"], no_contiene=["Cusco"])]
    suite = run_suite(cases, lambda c: resultado(answer=next(respuestas)))
    (o,) = suite.outcomes
    assert [f.split(":")[0] for f in o.failures] == ["contiene", "no_contiene"]


def test_repetitions_manda_sobre_las_repeticiones_del_caso():
    contador = {"n": 0}

    def execute(c: Case) -> RunResult:
        contador["n"] += 1
        return resultado()

    suite = run_suite([caso("a", repeticiones=5), caso("b", repeticiones=1)], execute, repetitions=2)
    assert contador["n"] == 4
    assert [o.runs for o in suite.outcomes] == [2, 2] and suite.total_runs == 4


@pytest.mark.parametrize("malo", [0, -1, 2.5, True, "3"])
def test_repetitions_invalido(malo):
    with pytest.raises(ValueError, match="repetitions"):
        run_suite([caso()], lambda c: resultado(), repetitions=malo)


def test_una_excepcion_cuenta_como_fallo_y_la_suite_continua():
    def execute(c: Case) -> RunResult:
        if c.id == "roto":
            raise RuntimeError("boom")
        return resultado()

    suite = run_suite([caso("roto", repeticiones=2), caso("sano")], execute)
    roto, sano = suite.outcomes
    assert (roto.runs, roto.passes, roto.rate) == (2, 0, 0.0)
    assert roto.failures == ["excepción: RuntimeError: boom"]  # un solo texto aunque falle 2 veces
    assert (sano.runs, sano.passes) == (1, 1)
    assert (suite.total_runs, suite.total_passes) == (3, 1)


def test_excepcion_solo_en_una_repeticion():
    estado = {"n": 0}

    def execute(c: Case) -> RunResult:
        estado["n"] += 1
        if estado["n"] == 2:
            raise ValueError("falló la segunda")
        return resultado()

    (o,) = run_suite([caso("a", repeticiones=3)], execute).outcomes
    assert (o.runs, o.passes) == (3, 2)
    assert o.failures == ["excepción: ValueError: falló la segunda"]


def test_el_mensaje_de_la_excepcion_va_en_una_linea_y_acotado():
    def execute(c: Case) -> RunResult:
        raise RuntimeError("linea1\nlinea2 " + "x" * 1000)

    (o,) = run_suite([caso()], execute).outcomes
    (texto,) = o.failures
    assert "\n" not in texto and len(texto) < 400 and texto.startswith("excepción: RuntimeError: linea1 linea2")


def test_keyboard_interrupt_no_se_traga():
    def execute(c: Case) -> RunResult:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_suite([caso()], execute)


def test_execute_que_no_devuelve_un_runresult_es_un_fallo_claro():
    (o,) = run_suite([caso()], lambda c: None).outcomes  # type: ignore[arg-type,return-value]
    assert o.passes == 0 and o.failures[0].startswith("error al calificar: AttributeError")


def test_caso_sin_criterios_no_cuenta_como_acierto():
    sin_criterios = Case(id="vacio", capa="x", pregunta="p", esperado=Expect())
    (o,) = run_suite([sin_criterios], lambda c: resultado()).outcomes
    assert o.passes == 0 and "sin criterios" in o.failures[0]


def test_suite_vacia_tiene_tasa_cero_sin_dividir_por_cero():
    suite = run_suite([], lambda c: resultado())
    assert (suite.outcomes, suite.total_runs, suite.total_passes, suite.rate) == ([], 0, 0, 0.0)


def test_ids_repetidos_en_run_suite_se_rechazan():
    with pytest.raises(ValueError, match="repetidos: a"):
        run_suite([caso("a"), caso("a")], lambda c: resultado())


def test_caso_armado_a_mano_con_repeticiones_invalidas():
    with pytest.raises(ValueError, match="repeticiones"):
        run_suite([caso("a", repeticiones=0)], lambda c: resultado())


def test_execute_recibe_el_caso_tal_cual():
    vistos: list[Case] = []
    c = caso("a")
    run_suite([c], lambda caso_: vistos.append(caso_) or resultado())
    assert vistos == [c] and vistos[0] is c
