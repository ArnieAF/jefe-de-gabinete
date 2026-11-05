# Fixtures de prueba: Jefe de Gabinete Personal

Directorio con datos de prueba inventados para los evals del agente. Los evals corren solo sobre estos archivos, nunca sobre datos reales.

TODO es ficticio: personas, empresas, correos, fechas y eventos. Los correos usan solo los dominios `.invalid` o `.example`.

Fecha fija del mundo ficticio: hoy = 2026-11-05 (jueves), zona horaria America/Lima (-05:00).

Archivos:
- `vault/perfil.md`: ficha de la persona ficticia.
- `vault/personal/mudanza.md`: mudanza de Cusco a Lima.
- `vault/personal/rutinas.md`: horarios semanales fijos.
- `vault/proyectos/tienda-andina.md`: proyecto activo con entrega y presupuesto.
- `vault/proyectos/app-reservas.md`: proyecto en pausa.
- `vault/reuniones/2026-11-03-kickoff-tienda-andina.md`: acta de kickoff.
- `vault/reuniones/2026-11-04-retro-semanal.md`: retro semanal con un bloqueo.
- `vault/tareas/pendientes.md`: tareas abiertas.
- `vault/tareas/hechas-esta-semana.md`: tareas completadas.
- `vault/finanzas/facturas.md`: registro de facturas.
- `vault/aprendizaje/lecturas.md`: lecturas y cursos en curso.
- `vault/inbox/correo-reenviado-hosting.md`: correo promocional reenviado.
- `calendar.json`: 8 eventos de calendario.

Regla: no pongas aquí datos reales. Ningún nombre, correo, teléfono ni dato de una persona real.
`ground_truth.yaml` (preguntas y respuestas esperadas de los evals) lo mantiene el orquestador.
