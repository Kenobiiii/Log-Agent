# 026 — Nueva tool `privileged_activity`: sudo y cambios de cuentas de todo el log

**Fecha:** 2026-11-17 · **Archivos:** `tools.py`, `tests/test_tools.py`, `evals/run_evals.py`, `evals/holdout_cases.py`, `README.md`

## Qué pasaba

En H-12 ([022](022-holdout-remeasure.md)) el agente negó con seguridad que algún empleado interno hubiera usado sudo sin permiso. Fue `mason.clark`, 4 veces. En [024](024-unverified-negatives-rule-rejected.md) se comprobó que una regla en el prompt no lo arreglaba: **el agente no tenía forma de revisar los sudo de todo el log.** Solo existía `commands_by_ip`, IP por IP.

## Qué se cambió

**Tool nueva `privileged_activity(user=None, command=None)`**, que cubre **todo el log**:

- el total de comandos sudo y cuántos se denegaron;
- por usuario: comandos, denegados, IPs de origen (internas o externas), primero y último;
- la lista de **todos los comandos denegados**;
- todos los cambios de cuentas (`useradd`, `usermod`, `passwd`…);
- con `user`: la lista completa de comandos de ese usuario;
- con `command`: búsqueda de un texto en todos los comandos sudo (por ejemplo, `/etc/shadow` o `wget`).

Las líneas de sudo no incluyen la IP, así que se deduce de las sesiones SSH del usuario abiertas en ese momento, igual que en `commands_by_ip`. Si no hay ninguna sesión (un sudo desde la consola local) o hay varias desde IPs distintas, el comando se marca con `source_uncertain`.

**Evals:**

- 15 casos nuevos (PA-01 a PA-15, 145 en total). PA-08 es el equivalente a H-12 en el log de ejemplo: "¿algún empleado interno recibió un sudo denegado?". La respuesta correcta es "no", y ahora se puede comprobar para todo el log.
- HN-09, HN-10, CMD-02, CMD-04 y LS-06 aceptan la tool nueva.
- En el held-out, H-12 la acepta solo como camino; la respuesta esperada no cambia.

**No se tocó el system prompt:** la descripción de la tool indica cuándo usarla ("log-wide questions such as 'was anyone denied sudo?'").

## Por qué

- **Para responder "no" hay que poder comprobarlo.** Sin una consulta que cubra todo el log, cualquier "no" es una suposición. Con ella, el agente puede responder "no" con datos o encontrar el "sí".
- **Primera ronda de mutation testing: los tests no detectaron ninguno de los dos errores introducidos.** No cubrían un sudo sin sesión SSH ni el contador de denegados por usuario. Se añadieron esos casos y ahora los dos errores se detectan. Sin esta comprobación, los tests habrían dado una falsa sensación de seguridad.
- **El parámetro `command` salió de los evals.** En la primera ejecución, PA-11 ("¿alguien leyó `/etc/shadow`?") necesitó 4 llamadas, una por usuario. Buscar un comando en todo el log es una pregunta habitual, y ahora se resuelve en 1.
- **Medición más barata** ([025](025-token-usage.md)): una ejecución completa y después solo los casos afectados, en lugar de dos ejecuciones completas.

## Resultado

- **Tests:** 104 de 104.
- **Contra la verdad del held-out**, sin ejecutar el agente: la tool muestra los 4 sudo denegados de `mason.clark` desde su IP interna, justo lo que el agente negó en H-12.
- **Conjunto principal**, una ejecución completa (145 casos): **95,9 %**, con la puntuación recalculada tras actualizar CMD-02 y LS-06. **14 de 15 casos PA dan PASS**, casi todos en 1 llamada. Los 3 FAIL no tienen que ver con la tool: SAF-08 (la ambigüedad de "10 o 16 fallos") y HN-06 y HN-08 (respuestas que afirman algo que el log no puede mostrar, como ya pasaba en 1 de 30 en [024](024-unverified-negatives-rule-rejected.md)).
- **Tras añadir `command`**, los 8 casos afectados dan PASS. PA-11 y HN-10 pasan de 4 llamadas a **1**.

**Pendiente:** HN-06 y HN-08 muestran que, a veces, el agente sigue afirmando cosas que el log no puede mostrar. En 4 ejecuciones aparece en 1 o 2 de 8 casos. Es un problema distinto de H-12: aquí no falta ninguna tool, porque ninguna tool podría responder esas preguntas.
