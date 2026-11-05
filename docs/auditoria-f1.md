# Auditoría del núcleo de F1 (harness y evals)

Fecha: 2026-11-05 · Rama revisada: `develop` (commit `eda2a17`) · Workflow `wf_cb5c9752-b91`

## Qué se revisó
El harness (`types`, `loop`, `eventlog`, `policy`, `ScriptedProvider`, herramientas de juguete), los evals (`cases`, `graders`, `suite`, `report`, `cli`, los 10 casos YAML),
las 907 pruebas, el CI, y los documentos que leerán el público y el asistente de IA de la PC de casa.
Tres lentes, un auditor por lente (solo lectura, pedidos como Fable): **seguridad y datos**, **corrección** y **UX / experiencia de desarrollo**. Cada hallazgo alto o medio
lo intentó refutar un segundo modelo (pedido como Opus). En total, 15 agentes, 263 llamadas a herramientas y unos 780 000 tokens.

## Qué encontró
23 hallazgos: **4 altos, 8 medios y 11 bajos**. Los 4 altos y 7 medios los confirmó el escéptico; 1 medio se refutó. Los bajos no pasaron por escéptico.

| Id | Sev. | Hallazgo (resumen) | Decisión |
|---|---|---|---|
| seg-1 | alto | El texto de una excepción del proveedor (con la URL y `?key=`) llegaba íntegro al registro, a los reportes y a la pantalla | **Corregido**: `redact.scrub`, conectado en registro, errores de herramientas y fallos de la suite; pruebas que fallan si se quita |
| seg-2 | alto | El guardián D10 trata `ollama` como local por su nombre (un Ollama remoto o en la nube pasaría) y solo se llama desde la CLI | **Convertido en requisitos obligatorios de T5/T11** con pruebas (`name` solo es `ollama` si host y modelo son locales); `PLAN.md` aclara quién debe llamar al guardián. No se puede cerrar en código porque el adaptador aún no existe |
| ux-1 | alto | La fila de T5 no bastaba para que un modelo pequeño escribiera el adaptador sin adivinar | **Corregido**: sección de requisitos de T5, T11 y T10 en `docs/F1-tareas.md` |
| ux-2 | alto | Nadie tenía asignado conectar los proveedores reales a la CLI | **Corregido**: nueva tarea T11 (y T10 para Gemini) |
| seg-3 / cor-1 | medio | El proveedor podía alterar las llamadas a herramientas después de devolverlas, y con ello la trayectoria que se califica | **Corregido**: copia profunda; prueba con un proveedor "mutante" |
| cor-2 | medio | `PLAN.md` decía que el harness aborta al arrancar si falla D10; el código solo lo hace la CLI | **Corregido**: el plan describe quién llama al guardián y cómo se verifica |
| ux-3 | medio | La guía de casa seguía apuntando a T1 y decía que Ollama podía esperar | **Corregido** |
| ux-4 | medio | Estado desactualizado en PLAN, README, AGENTS y el título de F1-tareas | **Corregido** |
| ux-5 | medio | Los reportes no registran proveedor ni modelo | **Asignado a T11** (se necesita cuando existan proveedores reales) |
| ux-6 | medio | El README afirmaba en presente lo que aún no existe y no explicaba los evals | **Corregido**: objetivo frente a estado real, sección Evals; también la descripción del repo en GitHub |
| seg-4 | medio | Solo el prompt y el rol `tool` protegen contra la inyección; la aprobación carece de contexto | **Refutado por el escéptico** (no es un fallo del código actual); queda como requisito de T5 y de F5 |
| seg-5 | bajo | `notes.read` sigue enlaces duros | Sin cambio: requiere acceso local de escritura al vault; límite documentado de la herramienta de juguete |
| seg-6 | bajo | Permisos 0o700 solo en la carpeta hoja del registro; reportes con permisos por defecto | Sin cambio (hoy solo hay datos falsos) |
| seg-7 | bajo | El CI instala pytest y pyyaml sin fijar versión | Sin cambio: riesgo bajo y aceptado por ahora |
| seg-8 | bajo | Una clave en variable de entorno es legible por procesos del asistente | **Corregido en parte**: `AGENTS.md` prohíbe imprimir variables de entorno |
| cor-3 | bajo | `no_contiene` pasa si no hay respuesta | Pospuesto: ningún caso actual depende solo de ese criterio |
| cor-4 | bajo | Documentos desactualizados | **Corregido** (junto con ux-4) |
| cor-5 | bajo | Un mensaje de error de la CLI nombra `--repo-root`, que ya no existe | **Corregido** |
| cor-6 | bajo | El `run_id` por defecto (a la segundo) puede chocar | Pospuesto |
| cor-7 | bajo | `load_cases` ignora `*.yml` en silencio | Pospuesto |
| ux-7 | bajo | Sin `PYTHONPATH` el aviso amable no aparece | Sin cambio: está documentado en README y guías |
| ux-8 | bajo | Pequeñas inconsistencias de mensajes de la CLI | **Corregido en parte** (el mensaje de `--repo-root`) |

## Qué respalda estas afirmaciones
- **Ejecutado por mí después de corregir:** la suite completa (925 pruebas pasan en Windows) y la mutación de cada corrección: quitando la copia profunda, el `scrub` del registro, el de los
  errores de herramienta o el de la suite, la prueba correspondiente falla.
- **Reproducido por un auditor y por un escéptico:** la fuga de la clave en seg-1 y la alteración de la trayectoria en seg-3 / cor-1.
- **Afirmado por los auditores sin verificación independiente:** los hallazgos bajos.

## Qué no tiene registro
- El modelo real de cada agente: solo consta el parámetro pedido al lanzarlos.
- Las transcripciones de los auditores, que viven en la carpeta de sesión de Claude Code de la PC de trabajo y no en este repositorio.
- Cualquier prueba con un modelo real o con Antigravity: los adaptadores de modelo aún no existen.
- El CI de GitHub con estas correcciones: se confirma tras el push.
