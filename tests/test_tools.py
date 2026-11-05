"""Pruebas del registro de herramientas y de las herramientas de juguete (tarea T3)."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from gabinete_harness.tools.registry import ToolRegistry
from gabinete_harness.tools.toy import (
    MAX_EMAIL_BODY_CHARS,
    MAX_EMAIL_SUBJECT_CHARS,
    MAX_EMAIL_TO_CHARS,
    MAX_NOTE_CHARS,
    default_toy_tools,
    make_calendar_tool,
    make_email_tool,
    make_notes_tool,
)
from gabinete_harness.types import Tool, ToolSpec


# --------------------------------------------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------------------------------------------
def run_tool(tool: Tool, arguments: object) -> object:
    """Ejecuta la herramienta, comprueba que devuelve un texto JSON y devuelve el valor ya decodificado."""
    text = tool.fn(arguments)  # type: ignore[arg-type]
    assert isinstance(text, str), f"fn debe devolver str, devolvió {type(text).__name__}"
    return json.loads(text)


def assert_error(result: object) -> str:
    assert isinstance(result, dict) and set(result) == {"error"}, f"se esperaba un error, llegó {result!r}"
    assert isinstance(result["error"], str) and result["error"]
    return result["error"]


def dummy_tool(name: str, requires_approval: bool = False) -> Tool:
    spec = ToolSpec(name=name, description="herramienta de prueba", schema={"type": "object"})
    return Tool(spec=spec, fn=lambda args: "ok", requires_approval=requires_approval)


@pytest.fixture
def toy(repo_root: Path) -> dict[str, Tool]:
    return {tool.name: tool for tool in default_toy_tools(repo_root)}


@pytest.fixture
def calendar_tool(toy: dict[str, Tool]) -> Tool:
    return toy["calendar.list_events"]


@pytest.fixture
def notes_tool(toy: dict[str, Tool]) -> Tool:
    return toy["notes.read"]


# --------------------------------------------------------------------------------------------------------------
# Registro
# --------------------------------------------------------------------------------------------------------------
class TestRegistro:
    def test_registrar_y_consultar(self):
        reg = ToolRegistry()
        a, b = dummy_tool("a.uno"), dummy_tool("b.dos", requires_approval=True)
        reg.register(a)
        reg.register(b)
        assert reg.get("a.uno") is a and reg.get("b.dos") is b
        assert len(reg) == 2
        assert "a.uno" in reg and "c.tres" not in reg

    def test_specs_y_names_conservan_el_orden_de_registro(self):
        reg = ToolRegistry()
        tools = [dummy_tool(n) for n in ("z", "a", "m")]
        for tool in tools:
            reg.register(tool)
        assert reg.names() == ["z", "a", "m"]
        assert reg.specs() == [t.spec for t in tools]
        assert all(isinstance(s, ToolSpec) for s in reg.specs())

    def test_specs_devuelve_una_lista_nueva(self):
        reg = ToolRegistry([dummy_tool("a")])
        reg.specs().clear()
        reg.names().clear()
        assert len(reg) == 1 and reg.names() == ["a"]

    def test_nombre_duplicado_da_valueerror_claro(self):
        reg = ToolRegistry()
        reg.register(dummy_tool("a.uno"))
        with pytest.raises(ValueError, match="a.uno"):
            reg.register(dummy_tool("a.uno"))
        assert len(reg) == 1  # el duplicado no reemplaza ni suma

    def test_get_de_nombre_desconocido_o_invalido_da_none(self):
        reg = ToolRegistry([dummy_tool("a")])
        assert reg.get("nope") is None
        assert reg.get("") is None
        assert reg.get(None) is None  # type: ignore[arg-type]
        assert reg.get(["a"]) is None  # type: ignore[arg-type]
        assert (None in reg) is False and (["a"] in reg) is False

    def test_registrar_algo_que_no_es_un_tool(self):
        with pytest.raises(TypeError):
            ToolRegistry().register("calendar.list_events")  # type: ignore[arg-type]

    def test_nombre_vacio_se_rechaza(self):
        with pytest.raises(ValueError):
            ToolRegistry().register(dummy_tool("  "))

    def test_registro_vacio(self):
        reg = ToolRegistry()
        assert len(reg) == 0 and reg.names() == [] and reg.specs() == []

    def test_constructor_acepta_un_iterable_y_detecta_duplicados(self, repo_root: Path):
        reg = ToolRegistry(default_toy_tools(repo_root))
        assert reg.names() == ["calendar.list_events", "notes.read", "email.send"]
        with pytest.raises(ValueError):
            ToolRegistry([dummy_tool("x"), dummy_tool("x")])


# --------------------------------------------------------------------------------------------------------------
# Especificaciones (lo que ve el modelo)
# --------------------------------------------------------------------------------------------------------------
class TestEspecificaciones:
    def test_default_toy_tools_nombres_y_aprobacion(self, toy: dict[str, Tool]):
        assert list(toy) == ["calendar.list_events", "notes.read", "email.send"]
        assert {n: t.requires_approval for n, t in toy.items()} == {
            "calendar.list_events": False,
            "notes.read": False,
            "email.send": True,
        }

    @pytest.mark.parametrize("name", ["calendar.list_events", "notes.read", "email.send"])
    def test_schema_json_estricto(self, toy: dict[str, Tool], name: str):
        spec = toy[name].spec
        assert isinstance(spec, ToolSpec) and spec.name == name
        assert len(spec.description) > 20
        schema = spec.schema
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) <= set(schema["properties"])
        assert set(schema["required"]) == set(schema["properties"])  # todos los argumentos son obligatorios
        for prop in schema["properties"].values():
            assert prop["type"] == "string" and prop["description"]
        json.dumps(schema)  # serializable

    def test_los_argumentos_del_schema_son_los_esperados(self, toy: dict[str, Tool]):
        props = {n: set(t.spec.schema["properties"]) for n, t in toy.items()}
        assert props == {
            "calendar.list_events": {"date"},
            "notes.read": {"path"},
            "email.send": {"to", "subject", "body"},
        }

    HOSTILE = [
        None, [], "texto", 5, {}, {"x": 1}, {1: 2}, {"": ""}, {"date": None}, {"date": 5}, {"path": None},
        {"path": {"a": 1}}, {"to": 1, "subject": 2, "body": 3}, {"date": "2026-11-05", "path": "perfil.md"},
        {"date": ["2026-11-05"]}, {"path": ["perfil.md"]}, {"date": "x" * 100_000}, {"path": "a" * 100_000},
        {"k" * 1000: 1},
    ]

    @pytest.mark.parametrize("name", ["calendar.list_events", "notes.read", "email.send"])
    def test_ninguna_herramienta_lanza_con_argumentos_hostiles(self, toy: dict[str, Tool], name: str):
        for arguments in self.HOSTILE:
            assert_error(run_tool(toy[name], arguments))


# --------------------------------------------------------------------------------------------------------------
# calendar.list_events
# --------------------------------------------------------------------------------------------------------------
def write_calendar(path: Path, events: object) -> Path:
    path.write_text(json.dumps(events), encoding="utf-8")
    return path


class TestCalendario:
    def test_eventos_del_dia_fijo_en_orden(self, calendar_tool: Tool):
        events = run_tool(calendar_tool, {"date": "2026-11-05"})
        assert [e["id"] for e in events] == ["cal-008", "cal-002"]

    def test_devuelve_todos_los_campos(self, calendar_tool: Tool):
        events = run_tool(calendar_tool, {"date": "2026-11-05"})
        assert events[0] == {
            "id": "cal-008",
            "titulo": "Cita con el dentista",
            "inicio": "2026-11-05T11:30:00-05:00",
            "fin": "2026-11-05T12:30:00-05:00",
            "asistentes": [],
            "lugar": "Consultorio Miraflores",
        }
        assert events[1]["asistentes"] == ["Rosa Huamán"]  # no se escapa a \uXXXX

    def test_coincide_con_ground_truth(self, repo_root: Path, calendar_tool: Tool):
        yaml = pytest.importorskip("yaml")
        truth = yaml.safe_load((repo_root / "fixtures" / "ground_truth.yaml").read_text(encoding="utf-8"))
        briefing = next(b for b in truth["briefing"] if b["id"] == "briefing-2026-11-05")
        events = run_tool(calendar_tool, {"date": "2026-11-05"})
        assert [e["id"] for e in events] == briefing["eventos_hoy"]

    def test_otro_dia_con_eventos(self, calendar_tool: Tool):
        assert [e["id"] for e in run_tool(calendar_tool, {"date": "2026-11-06"})] == ["cal-001"]

    def test_dia_sin_eventos_da_lista_vacia(self, calendar_tool: Tool):
        assert calendar_tool.fn({"date": "2026-11-07"}) == "[]"
        assert calendar_tool.fn({"date": "1999-12-31"}) == "[]"

    @pytest.mark.parametrize(
        "bad",
        [
            "", " ", "hoy", "05/11/2026", "2026-13-01", "2026-02-30", "2026-00-10", "2026-11-5", "26-11-05",
            "20261105", "2026-W45-4", "2026-11-05T10:00:00", "2026-11-05\n", " 2026-11-05", "2026-11-05 ",
            "２０２６-１１-０５",  # dígitos de ancho completo
            "2026-11-05; DROP TABLE", "0000-01-01",
        ],
    )
    def test_fecha_mal_formada_da_error(self, calendar_tool: Tool, bad: str):
        assert_error(run_tool(calendar_tool, {"date": bad}))

    @pytest.mark.parametrize("bad", [None, 20261105, ["2026-11-05"], {"d": 1}, True, 1.5])
    def test_fecha_de_tipo_incorrecto(self, calendar_tool: Tool, bad: object):
        assert_error(run_tool(calendar_tool, {"date": bad}))

    def test_argumento_ausente_o_de_mas(self, calendar_tool: Tool):
        assert "date" in assert_error(run_tool(calendar_tool, {}))
        msg = assert_error(run_tool(calendar_tool, {"date": "2026-11-05", "extra": "x"}))
        assert "extra" in msg
        assert_error(run_tool(calendar_tool, {"fecha": "2026-11-05"}))
        assert_error(run_tool(calendar_tool, None))

    def test_es_solo_lectura(self, repo_root: Path, calendar_tool: Tool):
        path = repo_root / "fixtures" / "calendar.json"
        before = path.read_bytes()
        calendar_tool.fn({"date": "2026-11-05"})
        calendar_tool.fn({"date": "no"})
        assert path.read_bytes() == before

    def test_la_fecha_local_es_la_del_propio_desfase(self, tmp_path: Path):
        cal = write_calendar(
            tmp_path / "cal.json",
            [
                {"id": "tarde", "inicio": "2026-11-05T23:30:00-05:00"},  # en UTC ya es el 06
                {"id": "madrugada", "inicio": "2026-11-06T01:00:00+09:00"},  # en UTC todavía es el 05
                {"id": "medio", "inicio": "2026-11-05T10:00:00-05:00"},
            ],
        )
        tool = make_calendar_tool(cal)
        assert [e["id"] for e in run_tool(tool, {"date": "2026-11-05"})] == ["medio", "tarde"]
        assert [e["id"] for e in run_tool(tool, {"date": "2026-11-06"})] == ["madrugada"]

    def test_orden_por_instante_con_desfases_distintos(self, tmp_path: Path):
        cal = write_calendar(
            tmp_path / "cal.json",
            [
                {"id": "lima", "inicio": "2026-11-05T10:00:00-05:00"},  # 15:00 UTC
                {"id": "tokio", "inicio": "2026-11-05T20:00:00+09:00"},  # 11:00 UTC (la hora de pared es mayor)
                {"id": "sin-desfase", "inicio": "2026-11-05T08:00:00"},  # se ordena como UTC; no debe lanzar
            ],
        )
        ids = [e["id"] for e in run_tool(make_calendar_tool(cal), {"date": "2026-11-05"})]
        assert ids == ["sin-desfase", "tokio", "lima"]

    def test_empates_conservan_el_orden_del_archivo(self, tmp_path: Path):
        cal = write_calendar(
            tmp_path / "cal.json",
            [{"id": n, "inicio": "2026-11-05T09:00:00-05:00"} for n in ("b", "a", "c")],
        )
        assert [e["id"] for e in run_tool(make_calendar_tool(cal), {"date": "2026-11-05"})] == ["b", "a", "c"]

    def test_eventos_mal_formados_se_ignoran(self, tmp_path: Path):
        cal = write_calendar(
            tmp_path / "cal.json",
            [
                "texto", None, 5, {"id": "sin-inicio"}, {"id": "basura", "inicio": "mañana"}, {"id": "num", "inicio": 5},
                {"id": "bueno", "inicio": "2026-11-05T09:00:00-05:00", "extra": {"k": [1, 2]}},
            ],
        )
        events = run_tool(make_calendar_tool(cal), {"date": "2026-11-05"})
        assert events == [{"id": "bueno", "inicio": "2026-11-05T09:00:00-05:00", "extra": {"k": [1, 2]}}]

    def test_calendario_ausente_o_corrupto_da_error_sin_ruta(self, tmp_path: Path):
        ausente = make_calendar_tool(tmp_path / "no-existe" / "cal.json")
        corrupto_path = tmp_path / "corrupto.json"
        corrupto_path.write_text("{no es json", encoding="utf-8")
        no_lista_path = write_calendar(tmp_path / "objeto.json", {"id": "x"})
        binario_path = tmp_path / "binario.json"
        binario_path.write_bytes(b"\xff\xfe\x00\x00")
        for path in (tmp_path / "no-existe" / "cal.json", corrupto_path, no_lista_path, binario_path):
            text = make_calendar_tool(path).fn({"date": "2026-11-05"})
            assert_error(json.loads(text))
            assert str(tmp_path) not in text and tmp_path.as_posix() not in text
        assert_error(run_tool(ausente, {"date": "2026-11-05"}))

    def test_lee_el_archivo_en_cada_llamada(self, tmp_path: Path):
        cal = write_calendar(tmp_path / "cal.json", [])
        tool = make_calendar_tool(cal)
        assert tool.fn({"date": "2026-11-05"}) == "[]"
        write_calendar(cal, [{"id": "nuevo", "inicio": "2026-11-05T09:00:00-05:00"}])
        assert [e["id"] for e in run_tool(tool, {"date": "2026-11-05"})] == ["nuevo"]


# --------------------------------------------------------------------------------------------------------------
# notes.read
# --------------------------------------------------------------------------------------------------------------
ESCAPES = [
    "../ground_truth.yaml",
    "..\\ground_truth.yaml",
    "perfil.md/../../README.md",
    "perfil.md\\..\\..\\README.md",
    "personal/../../ground_truth.yaml",
    "../../../../etc/passwd",
    "..",
    "../",
    "perfil.md/..",
    "....//ground_truth.yaml",  # "...." se normaliza a ".." en Windows
    ".. /ground_truth.yaml",
    "/etc/passwd",
    " /etc/passwd",
    "//etc/passwd",
    "\\Windows\\win.ini",
    "\\\\servidor\\recurso\\archivo.txt",
    "C:\\Windows\\win.ini",
    "C:/Windows/win.ini",
    "c:win.ini",
    "perfil.md:flujo",
    "",
    "   ",
    ".",
    "./",
    "personal",
    "personal/",
    "personal\\",
    "nul",
    "CON.txt",
    "aux",
    "perfil.md\x00.txt",
    "perfil.md\n",
]


class TestNotas:
    def test_lee_una_nota(self, notes_tool: Tool):
        result = run_tool(notes_tool, {"path": "perfil.md"})
        assert set(result) == {"path", "content"}
        assert result["path"] == "perfil.md"
        assert "Lima" in result["content"]
        assert "truncado" not in result["content"]

    @pytest.mark.parametrize(
        "path",
        ["personal/mudanza.md", "personal\\mudanza.md", "./personal/mudanza.md", "personal//mudanza.md", "  personal/mudanza.md  "],
    )
    def test_subcarpetas_y_variantes_de_separador(self, notes_tool: Tool, path: str):
        result = run_tool(notes_tool, {"path": path})
        assert result["path"] == "personal/mudanza.md"
        assert "Chuspi" in result["content"]

    @pytest.mark.parametrize("path", ESCAPES)
    def test_intentos_de_escape_dan_error_y_no_el_contenido(self, repo_root: Path, notes_tool: Tool, path: str):
        text = notes_tool.fn({"path": path})
        result = json.loads(text)
        assert_error(result)
        assert "content" not in result
        assert "briefing" not in text  # contenido de fixtures/ground_truth.yaml
        assert "Jefe de Gabinete" not in text  # contenido de README.md y del resto del repo
        assert str(repo_root) not in text and repo_root.as_posix() not in text

    def test_rutas_absolutas_reales_se_rechazan(self, repo_root: Path, notes_tool: Tool):
        fuera = repo_root / "fixtures" / "ground_truth.yaml"
        dentro = repo_root / "fixtures" / "vault" / "perfil.md"  # existe, pero una ruta absoluta nunca se acepta
        for absolute in (fuera, dentro):
            for text in (str(absolute), absolute.as_posix()):
                out = notes_tool.fn({"path": text})
                assert_error(json.loads(out))
                assert "Lima" not in out and "briefing" not in out

    def test_no_existe(self, notes_tool: Tool):
        assert "no existe" in assert_error(run_tool(notes_tool, {"path": "no-existe.md"}))
        assert_error(run_tool(notes_tool, {"path": "personal/no-existe.md"}))

    def test_directorio_da_error(self, notes_tool: Tool):
        assert "no es un archivo" in assert_error(run_tool(notes_tool, {"path": "personal"}))

    @pytest.mark.parametrize("bad", [None, 123, ["perfil.md"], {"path": "perfil.md"}, True, b"perfil.md"])
    def test_tipo_incorrecto(self, notes_tool: Tool, bad: object):
        assert_error(run_tool(notes_tool, {"path": bad}))

    def test_argumento_ausente_o_de_mas(self, notes_tool: Tool):
        assert "path" in assert_error(run_tool(notes_tool, {}))
        assert_error(run_tool(notes_tool, {"path": "perfil.md", "extra": 1}))
        assert_error(run_tool(notes_tool, {"ruta": "perfil.md"}))
        assert_error(run_tool(notes_tool, None))

    def test_ruta_demasiado_larga(self, notes_tool: Tool):
        assert_error(run_tool(notes_tool, {"path": "a/" * 600 + "x.md"}))

    def test_cada_nota_del_vault_se_puede_leer(self, repo_root: Path, notes_tool: Tool):
        vault = repo_root / "fixtures" / "vault"
        notas = sorted(p.relative_to(vault).as_posix() for p in vault.rglob("*.md"))
        assert len(notas) >= 10
        for rel in notas:
            result = run_tool(notes_tool, {"path": rel})
            assert result["path"] == rel and result["content"].strip(), rel


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Vault temporal con archivos dentro y "secretos" fuera (incluida una carpeta hermana con prefijo común)."""
    root = tmp_path / "vault"
    (root / "sub").mkdir(parents=True)
    (root / "nota.md").write_text("contenido de la nota", encoding="utf-8")
    (root / "sub" / "otra.md").write_text("otra nota", encoding="utf-8")
    (tmp_path / "secreto.txt").write_text("SECRETO-FUERA", encoding="utf-8")
    (tmp_path / "fuera").mkdir()
    (tmp_path / "fuera" / "secreto.txt").write_text("SECRETO-DIR-FUERA", encoding="utf-8")
    (tmp_path / "vault-hermano").mkdir()  # el nombre empieza igual que el del vault
    (tmp_path / "vault-hermano" / "secreto.txt").write_text("SECRETO-HERMANO", encoding="utf-8")
    return root


def symlink_or_skip(link: Path, target: Path, is_dir: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=is_dir)
    except (OSError, NotImplementedError):
        pytest.skip("el sistema no permite crear enlaces simbólicos")


@pytest.fixture
def junction(tmp_path: Path):
    """Crea uniones de directorio de Windows (no necesitan privilegios) y las quita al terminar sin seguirlas."""
    if sys.platform != "win32":
        pytest.skip("las uniones (junction) son solo de Windows")
    created: list[Path] = []

    def make(link: Path, target: Path) -> None:
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False)
        if proc.returncode != 0:
            pytest.skip("no se pudo crear una unión de directorio")
        created.append(link)

    yield make
    for link in created:
        try:
            os.rmdir(link)  # quita la unión sin tocar el destino
        except OSError:
            pass


class TestNotasEnVaultTemporal:
    def test_lee_dentro_del_vault(self, vault: Path):
        tool = make_notes_tool(vault)
        assert run_tool(tool, {"path": "nota.md"}) == {"path": "nota.md", "content": "contenido de la nota"}
        assert run_tool(tool, {"path": "sub/otra.md"})["content"] == "otra nota"

    def test_el_vault_puede_pasarse_como_str(self, vault: Path):
        assert run_tool(make_notes_tool(str(vault)), {"path": "nota.md"})["content"] == "contenido de la nota"  # type: ignore[arg-type]

    def test_rutas_absolutas_se_rechazan_aunque_apunten_adentro_o_afuera(self, tmp_path: Path, vault: Path):
        tool = make_notes_tool(vault)
        for absolute in (vault / "nota.md", tmp_path / "secreto.txt"):
            for text in (str(absolute), absolute.as_posix()):
                out = tool.fn({"path": text})
                assert_error(json.loads(out))
                assert "SECRETO" not in out and "contenido de la nota" not in out

    @pytest.mark.parametrize("path", ["/nota.md", "\\nota.md", "//nota.md", "/sub/otra.md", "\\sub\\otra.md"])
    def test_barra_inicial_se_rechaza_aunque_apunte_a_un_archivo_del_vault(self, vault: Path, path: str):
        """Sin esta regla, "/nota.md" se leería como "nota.md": una ruta absoluta nunca debe aceptarse."""
        out = make_notes_tool(vault).fn({"path": path})
        assert "absolutas" in assert_error(json.loads(out))
        assert "contenido de la nota" not in out and "otra nota" not in out

    @pytest.mark.parametrize("path", ["sub/../nota.md", "sub\\..\\nota.md", "./../vault/nota.md", "sub/./../nota.md"])
    def test_dotdot_se_rechaza_aunque_el_destino_quede_dentro(self, vault: Path, path: str):
        """Cualquier componente ".." se rechaza, aunque al resolverlo el archivo siga dentro del vault."""
        out = make_notes_tool(vault).fn({"path": path})
        assert "'..'" in assert_error(json.loads(out))
        assert "contenido de la nota" not in out

    @pytest.mark.parametrize(
        "path",
        ["../secreto.txt", "sub/../../secreto.txt", "..\\secreto.txt", "../vault-hermano/secreto.txt", "../fuera/secreto.txt"],
    )
    def test_dotdot_se_rechaza(self, vault: Path, path: str):
        out = make_notes_tool(vault).fn({"path": path})
        assert_error(json.loads(out))
        assert "SECRETO" not in out

    @pytest.mark.parametrize(
        "path",
        ["../secreto.txt", "/secreto.txt", "C:\\secreto.txt", "", "sub", "no-existe.md", "sub/no-existe.md", "nota.md/x",
         "nota.md:stream", "nul", None, 5],
    )
    def test_los_errores_no_incluyen_rutas_absolutas(self, tmp_path: Path, vault: Path, path: object):
        out = make_notes_tool(vault).fn({"path": path})
        assert_error(json.loads(out))
        for forbidden in (str(tmp_path), tmp_path.as_posix(), str(tmp_path.parent), str(vault), vault.as_posix()):
            assert forbidden not in out

    def test_vault_inexistente_da_error_sin_lanzar(self, tmp_path: Path):
        out = make_notes_tool(tmp_path / "no-existe").fn({"path": "nota.md"})
        assert_error(json.loads(out))
        assert str(tmp_path) not in out

    def test_enlace_simbolico_a_archivo_fuera_del_vault(self, tmp_path: Path, vault: Path):
        symlink_or_skip(vault / "enlace.md", tmp_path / "secreto.txt")
        out = make_notes_tool(vault).fn({"path": "enlace.md"})
        assert_error(json.loads(out))
        assert "SECRETO" not in out and str(tmp_path) not in out

    def test_enlace_simbolico_a_carpeta_fuera_del_vault(self, tmp_path: Path, vault: Path):
        symlink_or_skip(vault / "salida", tmp_path / "fuera", is_dir=True)
        out = make_notes_tool(vault).fn({"path": "salida/secreto.txt"})
        assert_error(json.loads(out))
        assert "SECRETO" not in out

    def test_enlace_simbolico_a_carpeta_hermana_con_prefijo_comun(self, tmp_path: Path, vault: Path):
        """Un `startswith` ingenuo aceptaría `vault-hermano` por empezar igual que `vault`; `is_relative_to` no."""
        symlink_or_skip(vault / "hermano", tmp_path / "vault-hermano", is_dir=True)
        out = make_notes_tool(vault).fn({"path": "hermano/secreto.txt"})
        assert_error(json.loads(out))
        assert "SECRETO" not in out

    def test_enlace_simbolico_hacia_adentro_si_se_permite(self, vault: Path):
        symlink_or_skip(vault / "atajo.md", vault / "nota.md")
        assert run_tool(make_notes_tool(vault), {"path": "atajo.md"})["content"] == "contenido de la nota"

    def test_ciclo_de_enlaces_no_lanza(self, tmp_path: Path, vault: Path):
        symlink_or_skip(vault / "a.md", vault / "b.md")
        symlink_or_skip(vault / "b.md", vault / "a.md")
        out = make_notes_tool(vault).fn({"path": "a.md"})
        assert_error(json.loads(out))
        assert str(tmp_path) not in out

    def test_union_de_directorio_hacia_afuera_se_rechaza(self, tmp_path: Path, vault: Path, junction):
        """En Windows sin privilegio de enlaces simbólicos, una unión (junction) es el equivalente que sí se puede crear."""
        junction(vault / "salida", tmp_path / "fuera")
        junction(vault / "hermano", tmp_path / "vault-hermano")
        tool = make_notes_tool(vault)
        for path in ("salida/secreto.txt", "hermano/secreto.txt"):
            out = tool.fn({"path": path})
            assert_error(json.loads(out))
            assert "SECRETO" not in out and str(tmp_path) not in out

    def test_union_de_directorio_hacia_adentro_si_se_permite(self, vault: Path, junction):
        junction(vault / "alias", vault / "sub")
        assert run_tool(make_notes_tool(vault), {"path": "alias/otra.md"})["content"] == "otra nota"

    def test_truncado_a_100000_caracteres(self, vault: Path):
        (vault / "larga.md").write_text("a" * MAX_NOTE_CHARS + "ZZZ", encoding="utf-8")
        result = run_tool(make_notes_tool(vault), {"path": "larga.md"})
        assert result["truncado"] is True
        assert result["content"].startswith("a" * MAX_NOTE_CHARS)
        assert "ZZZ" not in result["content"]
        assert "truncado" in result["content"][MAX_NOTE_CHARS:]
        assert len(result["content"]) < MAX_NOTE_CHARS + 200

    def test_justo_en_el_limite_no_se_trunca(self, vault: Path):
        (vault / "exacta.md").write_text("ñ" * MAX_NOTE_CHARS, encoding="utf-8")  # cuenta caracteres, no bytes
        result = run_tool(make_notes_tool(vault), {"path": "exacta.md"})
        assert result["content"] == "ñ" * MAX_NOTE_CHARS and "truncado" not in result

    def test_utf8_invalido_no_lanza(self, vault: Path):
        (vault / "raro.md").write_bytes(b"hola \xff\xfe mundo")
        result = run_tool(make_notes_tool(vault), {"path": "raro.md"})
        assert result["content"].startswith("hola ") and result["content"].endswith(" mundo")

    def test_archivo_vacio(self, vault: Path):
        (vault / "vacio.md").write_text("", encoding="utf-8")
        assert run_tool(make_notes_tool(vault), {"path": "vacio.md"}) == {"path": "vacio.md", "content": ""}

    def test_es_solo_lectura(self, vault: Path):
        before = sorted((p.relative_to(vault).as_posix(), p.read_bytes()) for p in vault.rglob("*") if p.is_file())
        tool = make_notes_tool(vault)
        for path in ("nota.md", "../x", "sub", "no-existe.md"):
            tool.fn({"path": path})
        after = sorted((p.relative_to(vault).as_posix(), p.read_bytes()) for p in vault.rglob("*") if p.is_file())
        assert before == after


# --------------------------------------------------------------------------------------------------------------
# email.send (simulada)
# --------------------------------------------------------------------------------------------------------------
VALID_EMAIL = {"to": "rosa@ejemplo.example", "subject": "Seguimiento", "body": "Hola Rosa, ¿confirmamos la reunión?"}


@pytest.fixture
def outbox() -> list:
    return []


@pytest.fixture
def email_tool(outbox: list) -> Tool:
    return make_email_tool(outbox)


@pytest.fixture
def sin_red(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cualquier intento de abrir un socket hace fallar la prueba."""

    def prohibido(*args: object, **kwargs: object) -> None:
        raise AssertionError("la herramienta simulada intentó usar la red")

    for name in ("socket", "create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, prohibido)


class TestCorreo:
    def test_requiere_aprobacion(self, email_tool: Tool):
        assert email_tool.requires_approval is True
        assert email_tool.name == "email.send"

    def test_envio_valido_llena_la_bandeja_y_no_usa_la_red(self, email_tool: Tool, outbox: list, sin_red: None):
        assert run_tool(email_tool, dict(VALID_EMAIL)) == {"status": "enviado (simulado)"}
        assert outbox == [VALID_EMAIL]

    def test_varios_envios_conservan_el_orden(self, email_tool: Tool, outbox: list):
        for i in range(3):
            run_tool(email_tool, {**VALID_EMAIL, "subject": f"n{i}"})
        assert [m["subject"] for m in outbox] == ["n0", "n1", "n2"]

    def test_la_bandeja_guarda_una_copia_de_los_datos(self, email_tool: Tool, outbox: list):
        arguments = dict(VALID_EMAIL)
        email_tool.fn(arguments)
        arguments["subject"] = "cambiado después"
        assert outbox[0]["subject"] == "Seguimiento"

    def test_asunto_y_cuerpo_vacios_son_validos(self, email_tool: Tool, outbox: list):
        assert run_tool(email_tool, {"to": "a@b.example", "subject": "", "body": ""}) == {"status": "enviado (simulado)"}
        assert len(outbox) == 1

    @pytest.mark.parametrize("missing", ["to", "subject", "body"])
    def test_falta_un_argumento(self, email_tool: Tool, outbox: list, missing: str):
        arguments = {k: v for k, v in VALID_EMAIL.items() if k != missing}
        assert missing in assert_error(run_tool(email_tool, arguments))
        assert outbox == []

    @pytest.mark.parametrize("field", ["to", "subject", "body"])
    @pytest.mark.parametrize("bad", [None, 5, ["x"], {"a": 1}, b"bytes", 1.5, True])
    def test_tipo_incorrecto(self, email_tool: Tool, outbox: list, field: str, bad: object):
        assert_error(run_tool(email_tool, {**VALID_EMAIL, field: bad}))
        assert outbox == []

    @pytest.mark.parametrize(
        "changes",
        [
            {"to": ""},
            {"to": "   "},
            {"to": "a@b.example\nBcc: otro@x.example"},
            {"subject": "linea1\r\nlinea2"},
            {"to": "a" * (MAX_EMAIL_TO_CHARS + 1)},
            {"subject": "s" * (MAX_EMAIL_SUBJECT_CHARS + 1)},
            {"body": "b" * (MAX_EMAIL_BODY_CHARS + 1)},
        ],
    )
    def test_valores_invalidos_no_envian(self, email_tool: Tool, outbox: list, changes: dict):
        assert_error(run_tool(email_tool, {**VALID_EMAIL, **changes}))
        assert outbox == []

    def test_justo_en_los_limites_es_valido(self, email_tool: Tool, outbox: list):
        arguments = {"to": "a" * MAX_EMAIL_TO_CHARS, "subject": "s" * MAX_EMAIL_SUBJECT_CHARS, "body": "b" * MAX_EMAIL_BODY_CHARS}
        assert run_tool(email_tool, arguments) == {"status": "enviado (simulado)"}
        assert len(outbox) == 1

    def test_argumentos_de_mas_o_mal_formados_no_envian(self, email_tool: Tool, outbox: list):
        assert_error(run_tool(email_tool, {**VALID_EMAIL, "cc": "otro@x.example"}))
        assert_error(run_tool(email_tool, {}))
        assert_error(run_tool(email_tool, None))
        assert_error(run_tool(email_tool, [VALID_EMAIL]))
        assert outbox == []

    def test_outbox_debe_ser_una_lista(self):
        with pytest.raises(TypeError):
            make_email_tool(None)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            make_email_tool("bandeja")  # type: ignore[arg-type]


class TestConjuntoPorDefecto:
    def test_usa_la_bandeja_recibida_aunque_este_vacia(self, repo_root: Path):
        box: list = []  # lista vacía = falsa: no debe sustituirse por otra
        email = default_toy_tools(repo_root, box)[2]
        run_tool(email, dict(VALID_EMAIL))
        assert box == [VALID_EMAIL]

    def test_sin_bandeja_funciona(self, repo_root: Path):
        email = default_toy_tools(repo_root)[2]
        assert run_tool(email, dict(VALID_EMAIL)) == {"status": "enviado (simulado)"}

    def test_las_herramientas_leen_de_fixtures(self, repo_root: Path):
        calendar, notes, _ = default_toy_tools(repo_root)
        assert [e["id"] for e in run_tool(calendar, {"date": "2026-11-05"})] == ["cal-008", "cal-002"]
        assert "Lima" in run_tool(notes, {"path": "perfil.md"})["content"]

    def test_acepta_repo_root_como_str(self, repo_root: Path):
        calendar = default_toy_tools(str(repo_root))[0]  # type: ignore[arg-type]
        assert [e["id"] for e in run_tool(calendar, {"date": "2026-11-05"})] == ["cal-008", "cal-002"]
