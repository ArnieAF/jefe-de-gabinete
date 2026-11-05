"""Pruebas de los reportes JSON/Markdown y su comparación entre corridas (tarea T7)."""
import json
from pathlib import Path

import pytest

from gabinete_evals.report import (
    build_report,
    compare,
    find_previous,
    load_previous,
    render_markdown,
    write_report,
)
from gabinete_evals.suite import CaseOutcome, SuiteResult


def suite_de(*outcomes: tuple[str, int, int]) -> SuiteResult:
    """Suite a partir de (id, repeticiones, aciertos)."""
    outs = [
        CaseOutcome(case_id=i, capa="herramientas", runs=n, passes=p, rate=p / n, failures=[] if p == n else ["contiene: faltan en la respuesta: 'x'"])
        for i, n, p in outcomes
    ]
    runs, passes = sum(o.runs for o in outs), sum(o.passes for o in outs)
    return SuiteResult(outcomes=outs, total_runs=runs, total_passes=passes, rate=passes / runs if runs else 0.0)


def escribir_reporte(carpeta: Path, run_id: str, *outcomes: tuple[str, int, int]) -> Path:
    json_path, _ = write_report(suite_de(*outcomes), carpeta, run_id)
    return json_path


# --- write_report -----------------------------------------------------------------------------------


def test_write_report_crea_json_y_markdown_con_la_tasa(tmp_path):
    json_path, md_path = write_report(suite_de(("a", 5, 4), ("b", 5, 5)), tmp_path, "20261105-1000")
    assert json_path == tmp_path / "report-20261105-1000.json"
    assert md_path == tmp_path / "report-20261105-1000.md"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["run_id"] == "20261105-1000" and data["total_runs"] == 10 and data["total_passes"] == 9
    assert data["rate"] == pytest.approx(0.9)
    assert [o["case_id"] for o in data["outcomes"]] == ["a", "b"]
    md = md_path.read_text(encoding="utf-8")
    assert "90.0 %" in md and "9/10" in md
    assert "| a | herramientas | 4/5 | 80.0 % | - |" in md
    assert "| b | herramientas | 5/5 | 100.0 % | - |" in md
    assert "Sin reporte anterior" in md


def test_write_report_crea_la_carpeta_de_salida_que_no_existe(tmp_path):
    salida = tmp_path / "no" / "existe" / "aun"
    json_path, md_path = write_report(suite_de(("a", 1, 1)), salida, "r1")
    assert json_path.is_file() and md_path.is_file()


def test_los_reportes_son_deterministas_y_no_llevan_marcas_de_hora(tmp_path):
    suite = suite_de(("a", 2, 1))
    j1, m1 = write_report(suite, tmp_path / "x", "r1")
    j2, m2 = write_report(suite, tmp_path / "y", "r1")
    assert j1.read_bytes() == j2.read_bytes() and m1.read_bytes() == m2.read_bytes()
    assert b"\r\n" not in j1.read_bytes() and b"\r\n" not in m1.read_bytes()


def test_el_markdown_lista_los_fallos(tmp_path):
    _, md_path = write_report(suite_de(("a", 2, 1)), tmp_path, "r1")
    md = md_path.read_text(encoding="utf-8")
    assert "## Fallos" in md and "- **a**" in md and "faltan en la respuesta" in md


@pytest.mark.parametrize("malo", ["", "../fuera", "a/b", "a\\b", "r:1", " r1", "r 1", ".oculto", "x" * 65, "ñ"])
def test_run_id_que_no_sirve_como_nombre_de_archivo_se_rechaza_sin_escribir(tmp_path, malo):
    salida = tmp_path / "salida"
    with pytest.raises(ValueError, match="run_id"):
        write_report(suite_de(("a", 1, 1)), salida, malo)
    assert not salida.exists()  # no se creó ni la carpeta


def test_no_pisa_un_reporte_existente_salvo_overwrite(tmp_path):
    write_report(suite_de(("a", 1, 1)), tmp_path, "r1")
    with pytest.raises(FileExistsError):
        write_report(suite_de(("a", 1, 0)), tmp_path, "r1")
    assert json.loads((tmp_path / "report-r1.json").read_text(encoding="utf-8"))["rate"] == 1.0  # intacto
    write_report(suite_de(("a", 1, 0)), tmp_path, "r1", overwrite=True)
    assert json.loads((tmp_path / "report-r1.json").read_text(encoding="utf-8"))["rate"] == 0.0


def test_salida_que_es_un_archivo_falla_con_oserror(tmp_path):
    archivo = tmp_path / "archivo"
    archivo.write_text("x", encoding="utf-8")
    with pytest.raises(OSError):
        write_report(suite_de(("a", 1, 1)), archivo, "r1")


def test_el_markdown_escapa_barras_y_saltos_en_ids_y_fallos(tmp_path):
    outcome = CaseOutcome(case_id="a|b", capa="x\ny", runs=1, passes=0, rate=0.0, failures=["linea1\nlinea2 | tubo"])
    suite = SuiteResult(outcomes=[outcome], total_runs=1, total_passes=0, rate=0.0)
    _, md_path = write_report(suite, tmp_path, "r1")
    md = md_path.read_text(encoding="utf-8")
    assert "| a\\|b | x y | 0/1 | 0.0 % | - |" in md
    assert "linea1 linea2 \\| tubo" in md


# --- write_report con comparación -------------------------------------------------------------------


def test_write_report_compara_con_el_reporte_anterior_de_la_carpeta(tmp_path):
    escribir_reporte(tmp_path, "20261104-0900", ("a", 5, 3), ("b", 5, 5), ("vieja", 2, 2))
    json_path, md_path = write_report(suite_de(("a", 5, 4), ("b", 5, 5), ("nueva", 1, 1)), tmp_path, "20261105-1000")
    md = md_path.read_text(encoding="utf-8")
    assert "| a | herramientas | 4/5 | 80.0 % | +20.0 pp |" in md
    assert "| b | herramientas | 5/5 | 100.0 % | 0.0 pp |" in md
    assert "| nueva | herramientas | 1/1 | 100.0 % | nuevo |" in md
    assert "20261104-0900" in md and "vieja" in md  # anterior y caso desaparecido
    comparison = json.loads(json_path.read_text(encoding="utf-8"))["comparison"]
    assert comparison["previous_run_id"] == "20261104-0900"
    assert comparison["cases"]["vieja"]["status"] == "removed"


def test_un_json_anterior_roto_se_avisa_en_el_reporte_y_no_lanza(tmp_path):
    (tmp_path / "report-20261104-0900.json").write_text("{ esto no es json", encoding="utf-8")
    json_path, md_path = write_report(suite_de(("a", 1, 1)), tmp_path, "20261105-1000")
    assert "ilegible" in md_path.read_text(encoding="utf-8") and "## Avisos" in md_path.read_text(encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["warnings"]


# --- load_previous / find_previous ------------------------------------------------------------------


def test_load_previous_elige_el_inmediatamente_anterior(tmp_path):
    for rid in ("20261101", "20261103", "20261105", "20261107"):
        escribir_reporte(tmp_path, rid, ("a", 1, 1))
    assert load_previous(tmp_path, "20261105")["run_id"] == "20261103"  # no el 05 (igual) ni el 07 (posterior)
    assert load_previous(tmp_path, "20261104")["run_id"] == "20261103"
    assert load_previous(tmp_path, "20261108")["run_id"] == "20261107"
    assert load_previous(tmp_path, "20261101") is None  # nada anterior


def test_load_previous_ordena_los_run_id_como_texto(tmp_path):
    for rid in ("run-9", "run-10"):
        escribir_reporte(tmp_path, rid, ("a", 1, 1))
    # como texto "run-10" < "run-9"; el anterior a "run-9" es "run-10"
    assert load_previous(tmp_path, "run-9")["run_id"] == "run-10"


def test_load_previous_ignora_archivos_que_no_son_report_json(tmp_path):
    escribir_reporte(tmp_path, "r1", ("a", 1, 1))
    (tmp_path / "report-r2.md").write_text("# md", encoding="utf-8")
    (tmp_path / "otro-r2.json").write_text("{}", encoding="utf-8")
    (tmp_path / "report-.json").write_text("{}", encoding="utf-8")
    (tmp_path / "report-r1.json.bak").write_text("{}", encoding="utf-8")
    (tmp_path / "report-r1b.json").mkdir()  # una carpeta con nombre de reporte
    previo, avisos = find_previous(tmp_path, "r9")
    assert previo["run_id"] == "r1" and avisos == []


def test_load_previous_ignora_json_roto_con_aviso_y_usa_el_siguiente(tmp_path):
    escribir_reporte(tmp_path, "r1", ("a", 1, 1))
    (tmp_path / "report-r2.json").write_text("{ roto", encoding="utf-8")
    previo = load_previous(tmp_path, "r3")
    assert previo["run_id"] == "r1"
    assert len(previo["avisos"]) == 1 and "report-r2.json" in previo["avisos"][0]


def test_load_previous_devuelve_none_si_solo_hay_json_roto(tmp_path):
    (tmp_path / "report-r1.json").write_text("{ roto", encoding="utf-8")
    assert load_previous(tmp_path, "r2") is None
    previo, avisos = find_previous(tmp_path, "r2")
    assert previo is None and len(avisos) == 1  # el aviso no se pierde con find_previous


def test_load_previous_ignora_json_valido_pero_que_no_es_un_reporte(tmp_path):
    (tmp_path / "report-r1.json").write_text("[1, 2, 3]", encoding="utf-8")
    (tmp_path / "report-r2.json").write_text('{"run_id": "r2", "rate": "alta", "outcomes": []}', encoding="utf-8")
    (tmp_path / "report-r3.json").write_text('{"run_id": "otro", "rate": 1.0, "outcomes": []}', encoding="utf-8")
    (tmp_path / "report-r4.json").write_text('{"run_id": "r4", "rate": 1.0, "outcomes": [{"case_id": 5}]}', encoding="utf-8")
    previo, avisos = find_previous(tmp_path, "r9")
    assert previo is None and len(avisos) == 4


def test_load_previous_ignora_bytes_no_utf8_y_json_profundisimo(tmp_path):
    (tmp_path / "report-r1.json").write_bytes(b"\xff\xfe\x00")
    (tmp_path / "report-r2.json").write_text("[" * 100_000, encoding="utf-8")
    previo, avisos = find_previous(tmp_path, "r9")
    assert previo is None and len(avisos) == 2


def test_load_previous_con_carpeta_inexistente_o_vacia_devuelve_none(tmp_path):
    assert load_previous(tmp_path / "no-existe", "r1") is None
    assert load_previous(tmp_path, "r1") is None
    assert find_previous(tmp_path / "no-existe", "r1") == (None, [])


def test_load_previous_sin_avisos_no_agrega_la_clave(tmp_path):
    escribir_reporte(tmp_path, "r1", ("a", 1, 1))
    assert "avisos" not in load_previous(tmp_path, "r2")


# --- compare ----------------------------------------------------------------------------------------


def reporte(run_id: str, *outcomes: tuple[str, int, int]) -> dict:
    return build_report(suite_de(*outcomes), run_id)


def test_compare_sin_anterior():
    assert compare(reporte("r2", ("a", 1, 1)), None) == {"previous_run_id": None, "total_delta_pp": None, "cases": {}}


def test_compare_diferencia_total_y_por_caso_en_puntos_porcentuales():
    previo = reporte("r1", ("a", 5, 3), ("b", 5, 5), ("c", 4, 3))
    actual = reporte("r2", ("a", 5, 4), ("b", 5, 5), ("c", 4, 1))
    result = compare(actual, previo)
    assert result["previous_run_id"] == "r1"
    # total: antes 11/14 (78.57 %), ahora 10/14 (71.43 %) -> -7.14 pp
    assert result["total_delta_pp"] == -7.14
    assert result["cases"]["a"] == {"status": "compared", "rate": 0.8, "previous_rate": 0.6, "delta_pp": 20.0}
    assert result["cases"]["b"]["delta_pp"] == 0.0
    assert result["cases"]["c"]["delta_pp"] == -50.0


def test_compare_marca_casos_nuevos_y_desaparecidos():
    previo = reporte("r1", ("a", 1, 1), ("vieja", 2, 1))
    actual = reporte("r2", ("a", 1, 0), ("nueva", 3, 3))
    cases = compare(actual, previo)["cases"]
    assert cases["a"]["status"] == "compared" and cases["a"]["delta_pp"] == -100.0
    assert cases["nueva"] == {"status": "new", "rate": 1.0, "previous_rate": None, "delta_pp": None}
    assert cases["vieja"] == {"status": "removed", "rate": None, "previous_rate": 0.5, "delta_pp": None}
    assert list(cases) == ["a", "nueva", "vieja"]  # primero los del actual y luego los desaparecidos


def test_compare_no_devuelve_menos_cero_ni_ruido_de_coma_flotante():
    previo = reporte("r1", ("a", 3, 1))
    delta = compare(reporte("r2", ("a", 3, 1)), previo)["total_delta_pp"]
    assert delta == 0.0 and str(delta) == "0.0"
    assert compare(reporte("r2", ("a", 5, 4)), reporte("r1", ("a", 5, 3)))["total_delta_pp"] == 20.0


def test_compare_no_modifica_sus_entradas():
    previo, actual = reporte("r1", ("a", 1, 1)), reporte("r2", ("a", 1, 0))
    copia = (json.dumps(previo), json.dumps(actual))
    compare(actual, previo)
    assert (json.dumps(previo), json.dumps(actual)) == copia


def test_render_markdown_cambio_negativo_y_casos_desaparecidos():
    previo = reporte("r1", ("a", 4, 4), ("vieja", 1, 1))
    actual = reporte("r2", ("a", 4, 3))
    actual["comparison"] = compare(actual, previo)
    md = render_markdown(actual)
    assert "-25.0 pp" in md and "vieja" in md and "(tasa anterior 100.0 %)" in md
