#!/usr/bin/env python3
"""Comprueba que fixtures/ es coherente con fixtures/ground_truth.yaml.

Uso:  python scripts/verify_fixtures.py [raiz_del_repo]
Requiere PyYAML (pip install pyyaml). Termina con código 1 si alguna comprobación falla.

Qué verifica:
  - cada nota tiene frontmatter (titulo, creado, tags) y no es posterior a "hoy";
  - cada enlace [[...]] apunta a una nota que existe;
  - cada frase "contiene" de ground_truth aparece en sus notas relevantes;
  - el calendario es JSON válido, con campos completos, zona -05:00 y fin posterior al inicio;
  - los eventos de hoy y los vencimientos del briefing coinciden con calendario y tareas;
  - el conflicto plantado de agenda (evento fuera del horario declarado) existe de verdad;
  - la instrucción inyectada está en su nota y la nota no tiene rótulos que delaten la prueba;
  - los correos de los fixtures usan solo dominios .invalid o .example.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
FX = ROOT / "fixtures"
VAULT = FX / "vault"

errors: list[str] = []
checks = 0


def check(cond: bool, msg: str) -> None:
    global checks
    if cond:
        checks += 1
    else:
        errors.append(msg)


gt = yaml.safe_load((FX / "ground_truth.yaml").read_text(encoding="utf-8"))
hoy = dt.date.fromisoformat(gt["hoy"])
notes = {p.relative_to(VAULT).as_posix(): p.read_text(encoding="utf-8") for p in sorted(VAULT.rglob("*.md"))}
check(len(notes) > 0, "no hay notas en fixtures/vault")

# 1) Frontmatter y fechas
for rel, text in notes.items():
    parts = text.split("---", 2)
    if not text.startswith("---") or len(parts) < 3:
        errors.append(f"{rel}: sin frontmatter")
        continue
    meta = yaml.safe_load(parts[1])
    if not isinstance(meta, dict) or not all(k in meta for k in ("titulo", "creado", "tags")):
        errors.append(f"{rel}: frontmatter incompleto (se piden titulo, creado y tags)")
        continue
    check(isinstance(meta["creado"], dt.date) and meta["creado"] <= hoy, f"{rel}: 'creado' falta o es posterior a hoy ({hoy})")

# 2) Enlaces [[...]]
for rel, text in notes.items():
    for target in re.findall(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]", text):
        check(f"{target.strip()}.md" in notes, f"{rel}: el enlace [[{target}]] no apunta a ninguna nota")

# 3) Preguntas de recuperación
ids: list[str] = []
for caso in gt.get("rag", []):
    ids.append(caso["id"])
    faltan = [n for n in caso["notas_relevantes"] if n not in notes]
    check(not faltan, f"{caso['id']}: notas inexistentes {faltan}")
    union = "\n".join(notes.get(n, "") for n in caso["notas_relevantes"]).lower()
    for frase in caso["contiene"]:
        check(frase.lower() in union, f"{caso['id']}: '{frase}' no aparece en {caso['notas_relevantes']}")
for caso in gt.get("memoria", []) + gt.get("seguridad", []) + gt.get("briefing", []):
    ids.append(caso["id"])
check(len(ids) == len(set(ids)), "hay ids repetidos en ground_truth.yaml")

# 4) Calendario
cal = json.loads((FX / "calendar.json").read_text(encoding="utf-8"))
por_id = {e["id"]: e for e in cal}
check(len(por_id) == len(cal), "calendar.json: ids de evento repetidos")
for e in cal:
    for campo in ("id", "titulo", "inicio", "fin", "asistentes", "lugar"):
        check(campo in e, f"{e.get('id', '?')}: falta el campo '{campo}'")
    try:
        ini, fin = dt.datetime.fromisoformat(e["inicio"]), dt.datetime.fromisoformat(e["fin"])
        check(fin > ini, f"{e['id']}: el fin no es posterior al inicio")
        check(ini.utcoffset() == dt.timedelta(hours=-5), f"{e['id']}: la zona horaria no es -05:00")
    except (KeyError, ValueError) as ex:
        errors.append(f"{e.get('id', '?')}: fecha inválida ({ex})")

# 5) Briefing y conflicto plantado
for b in gt.get("briefing", []):
    de_hoy = [e["id"] for e in sorted(cal, key=lambda e: e["inicio"]) if e["inicio"].startswith(hoy.isoformat())]
    check(de_hoy == b["eventos_hoy"], f"{b['id']}: eventos de hoy {de_hoy} != ground_truth {b['eventos_hoy']}")
    for tarea in b.get("vencen_en_5_dias", []):
        check(tarea.lower() in notes.get("tareas/pendientes.md", "").lower(), f"{b['id']}: la tarea '{tarea}' no está en tareas/pendientes.md")
    for c in b.get("conflictos_agenda", []):
        ev = por_id.get(c["evento"])
        hora = re.search(r"(\d{1,2}):(\d{2})", c["regla"])
        check(ev is not None and hora is not None, f"{b['id']}: conflicto mal definido ({c})")
        if ev and hora:
            limite = dt.time(int(hora.group(1)), int(hora.group(2)))
            check(dt.datetime.fromisoformat(ev["inicio"]).time() >= limite, f"{c['evento']} no cae después de las {limite}: el conflicto plantado no existe")
        check(c["regla"].lower() in notes.get("personal/rutinas.md", "").lower(), f"la regla '{c['regla']}' no está en personal/rutinas.md")

# 6) Seguridad: la instrucción inyectada está y no hay rótulos delatores
for s in gt.get("seguridad", []):
    texto = notes.get(s["nota"], "")
    check(s["instruccion_inyectada"].lower() in texto.lower(), f"{s['id']}: la instrucción inyectada no está en {s['nota']}")
    for malo in ("inyecc", "fixture", "prueba", "ataque", "malicios"):
        check(malo not in texto.lower(), f"{s['nota']}: contiene el rótulo delator '{malo}'")

# 7) Solo correos ficticios
for p in sorted(FX.rglob("*")):
    if p.is_file() and p.suffix in {".md", ".json", ".yaml"}:
        for m in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", p.read_text(encoding="utf-8")):
            check(m.endswith((".invalid", ".example")), f"{p.relative_to(ROOT).as_posix()}: correo no ficticio '{m}'")

print(f"comprobaciones correctas: {checks}")
if errors:
    print(f"ERRORES ({len(errors)}):")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print("fixtures OK")
