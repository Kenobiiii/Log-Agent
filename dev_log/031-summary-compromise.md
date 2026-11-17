# 031 — Los resúmenes siempre dicen si hubo compromisos

**Fecha:** 2026-11-17 · **Archivos:** `tools.py`, `tests/test_tools.py`, `evals/run_evals.py`

## Qué pasaba

En los experimentos de injection ([029](029-prompt-injection.md), [030](030-subtle-injection.md)), la pregunta *"Give me a short summary of this log for the on-call engineer"* a veces no mencionaba que dos cuentas habían sido comprometidas, **incluso con el log limpio**. El resumen se quedaba en las cifras de `log_summary` (4.147 fallos, usuarios más atacados…). Un resumen así es peligroso: da una falsa sensación de tranquilidad.

## Medición previa

Se crearon 4 casos de resumen (LS-19 a LS-22), evaluados por el juez: pasan si el resumen dice que alguna cuenta fue comprometida. Cada uno se repitió 5 veces con el agente sin cambios:

- **Menciona el compromiso en 19 de 20**, mejor de lo que hacía pensar el experimento de injection.
- Pero hace **4,7 llamadas de media** para conseguirlo: investiga casi todo cada vez.
- Cuando el resumen es muy corto (LS-22, *"two-line status update for the team channel"*), a veces se queda con 2 llamadas y se salta el compromiso.

El problema era doble: **poco fiable cuando va rápido, y caro cuando es fiable.**

## Qué se cambió

**`log_summary` incluye `security_signals`**: el número de logins desde IPs externas, la lista de cuentas e IPs (con los fallos previos), los sudo denegados y las cuentas creadas durante el log. Su descripción indica que es la base de cualquier resumen y que un resumen debe decir si hubo compromisos.

La nota de las señales decía al principio *"check it with external_logins / commands_by_ip"*, y el agente llamaba a `external_logins`, que repite los mismos datos. Se cambió por *"external_login_accounts already lists them; use commands_by_ip only if you need what an IP did"*.

En LS-19, 20 y 21 (resúmenes de "qué ha pasado") el número esperado de llamadas pasa de 2 a 3. El agente consulta qué hizo cada IP atacante, y eso es razonable en un resumen de incidentes. LS-22 (dos líneas) mantiene 2.

## Por qué

- **Los datos importantes, en la tool.** Es el mismo principio que en [007](007-subnet-breakdown.md), [012](012-log-summary-description.md) y [016](016-top-ips-count.md). Si para saber si hubo un compromiso hay que acordarse de llamar a otra tool, a veces no se hará. Si viene en el resumen, no se puede pasar por alto.
- **No se tocó el prompt.** Se probó primero el arreglo en la tool, como estaba previsto, y fue suficiente.
- **Se cambió una sola cosa cada vez:** primero las señales, después la nota. Así se vio que la nota influía en las llamadas, aunque poco.

## Resultado

Casos de resumen (LS-19 a LS-22), 5 repeticiones cada uno:

| | Antes | Con señales | Con señales y nota ajustada |
|---|---|---|---|
| Menciona el compromiso | 19/20 | **20/20** | **20/20** |
| Llamadas de media | 4,7 | 3,9 | 3,7 |
| LS-22 (dos líneas): llamadas | 2–4 (1 fallo) | **1** | **1** |

- **Foto del log de ejemplo:** solo cambia `log_summary`, y solo con el campo nuevo.
- **Tests:** 114 de 114. Contar todos los sudo como denegados hace fallar un test; se comprobó introduciendo ese error.
- **Conjunto principal**, una ejecución completa (154 casos): en los 150 comunes, **97,0 % → 98,0 %**, con las mismas llamadas de media y algo menos de tokens (5.258 → 5.141 por caso), a pesar de que `log_summary` devuelve más datos. Las dos regresiones (CMD-03, UB-15) son ruido: ya habían variado así otras veces y no usan las señales nuevas.
