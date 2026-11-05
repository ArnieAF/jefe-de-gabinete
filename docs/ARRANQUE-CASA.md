# Seguir el proyecto desde tu PC de casa

Pensado para empezar sin pagar nada y con tu asistente de IA de siempre (Antigravity con sus modelos gratuitos).

## 1. Instalar lo que falta
- **Git**, **Python 3.12** y **Docker Desktop** (en Windows usa WSL2; cuánta RAM consume en tu PC no está medido).
- **Ollama** puede esperar: se necesita para la tarea F1-T5, no para empezar.

## 2. Bajar el proyecto y comprobar que arranca
```powershell
git clone https://github.com/ArnieAF/jefe-de-gabinete.git
cd jefe-de-gabinete
git switch develop
Copy-Item .env.example .env
```
Edita `.env` con el Bloc de notas (no con el IDE) y escribe en `POSTGRES_PASSWORD` una contraseña **desechable**, sin `$` ni comillas: la base solo
escucha en tu propia PC. `.env` no se sube al repo. Después:
```powershell
docker compose up -d --wait
docker compose exec db psql -U gabinete -d gabinete -c "\dx"     # debe listar la extensión vector
python -m venv .venv                                              # usa Python 3.12
.\.venv\Scripts\Activate.ps1                                      # si PowerShell lo bloquea: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install pyyaml pytest
python scripts/verify_fixtures.py .                               # debe terminar con "fixtures OK"
```
El repo es público: clonar no pide iniciar sesión. Para subir cambios (`git push`) sí te pedirá iniciar sesión en GitHub con la cuenta `ArnieAF`.

Cuando llegue la tarea T5, la clave de Gemini (si la usas) ponla tú como variable de entorno de tu usuario en lugar de dejarla en un archivo:
`[Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "<tu clave>", "User")`. No la pegues en el chat.

## 3. Medir tu hardware
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\hardware.ps1
```
Su salida no incluye tu usuario ni rutas. Con ella se elige el modelo local que de verdad corre en tu PC.

## 4. Abrir el proyecto en Antigravity
Abre **solo la carpeta del repo**. Antigravity lee `AGENTS.md` por sí solo (lo indica su documentación oficial), así que ya conoce las reglas
del proyecto. Pega este mensaje, con la salida del paso 3 donde dice `<hardware>`:

```
Estoy en mi PC de casa, sin GPU y sin pagar nada. Lee AGENTS.md, docs/F1-tareas.md y PLAN.md (secciones 1, 5 y 6).
Mi hardware es: <hardware>. Anótalo en PLAN.md, sección 12, pregunta 3.
Haz SOLO la tarea T1 (después seguimos con T2, T3...). Rama feat/f1-t1 desde develop, commits pequeños con push después de cada uno,
verifica ejecutando las pruebas, y si pasan únela a develop con --no-ff y sube develop. No toques main ni mis datos reales.
```

Si se acaban los tokens gratuitos a mitad de una tarea, no pasa nada: lo hecho está en commits subidos y `docs/F1-tareas.md` dice qué sigue.
Mañana, o con otro modelo, se pega el mismo mensaje cambiando el número de tarea.

No pude verificar si Antigravity respeta `.gitignore` o si tiene una forma de excluir archivos de su contexto: revísalo en su documentación o en sus
ajustes. Mientras tanto, evita abrir `.env` en el IDE.

## 5. Empezar con datos reales, sin regalarlos

**Primero, qué pasa con lo que lee tu asistente.** Según los términos oficiales de Antigravity (consultados el 2026-11-05), Google registra
datos del usuario y de uso ("Interactions") y los usa para mejorar sus productos y su aprendizaje automático; sus empleados y contratistas
pueden revisarlos. El ajuste de privacidad no cubre el uso para prestar el servicio, y los términos no aclaran si tu código y tus mensajes
cuentan. Hay que asumir que **todo lo que el asistente lee puede llegar a Google.** Con el nivel gratuito de la API de Gemini pasa algo
parecido (su página de precios indica que el contenido se usa para mejorar productos).

**Reglas para usar tus notas reales:**
1. Las notas reales viven **fuera del repo y fuera de la carpeta que abres en Antigravity**, por ejemplo `C:\GabineteDatos\vault-real`.
2. Empieza con 5 a 15 notas poco sensibles (proyectos, pendientes, aprendizaje). Deja fuera finanzas, salud, claves, datos de otras personas y trabajo confidencial.
3. Los programas que lean esas notas los ejecutas **tú**, en una terminal aparte (no el asistente), con un modelo **local**, y no pegas sus resultados en el chat del asistente.
4. Los registros de esas ejecuciones también van fuera del repo (variable `GABINETE_LOG_DIR`, tarea T4).
5. No se ejecuta nada con datos reales hasta que exista el guardián de la tarea F1-T6.
6. Los modelos gratuitos en la nube solo ven los datos falsos de `fixtures/`.

**Cuándo:** lo primero que lee notas es F2 (servidor MCP de notas) y F3 (RAG). Mañana todavía no hay nada que use datos reales:
mientras tanto, prepara la copia curada de notas y decide qué entra.
