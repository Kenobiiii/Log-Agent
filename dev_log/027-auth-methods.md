# 027 — Desglose por método de autenticación

**Fecha:** 2026-11-17 · **Archivos:** `tools.py`, `tests/test_tools.py`, `evals/run_evals.py`, `README.md`

## Qué pasaba

Desde [018](018-parser-formats.md) el parser guarda el método de cada intento (`password`, `publickey`, `keyboard-interactive`), pero **ninguna tool lo exponía**. En el held-out ([022](022-holdout-remeasure.md)) quedaban dos FAIL por eso:

- **H-20:** "¿Cuántos logins usaron keyboard-interactive?" El agente respondió que no podía saberlo.
- **H-18:** "¿Hubo fallos de clave pública? ¿Desde qué IPs y para qué usuarios?" Lo mismo.

## Qué se cambió

En lugar de crear una tool nueva, se ampliaron dos que ya existían:

- **`log_summary`** añade `successful_logins_by_method` y `failed_attempts_by_method`.
- **`top_failed_ips`** acepta un parámetro opcional `method`. Con él, el ranking cuenta solo los fallos de ese método y cada IP incluye los usuarios probados. Sin él, la salida es exactamente la de antes. Un método desconocido devuelve un error con los valores válidos.
- 3 tests nuevos (107 en total).
- 5 casos nuevos en el conjunto principal (LS-16 a 18, TF-16 y 17; 150 en total). En dos de ellos ("¿hubo fallos de clave pública?") la respuesta correcta es "no", y ahora es comprobable.
- CMD-05, CMD-09 y CMD-14 aceptan `privileged_activity`. No tiene que ver con este cambio: en esta ejecución el agente la usó para preguntas sobre los comandos de un usuario (en CMD-09, con 2 llamadas en lugar de 4), y esos casos se habían quedado sin actualizar en [026](026-privileged-activity.md).

## Por qué

- **Ampliar en lugar de crear.** Un desglose por método es un dato más del resumen y un filtro más del ranking, no una pregunta distinta. Cada tool nueva es una opción más entre las que el modelo tiene que elegir.
- **El parámetro no cambia la salida normal.** Sin `method`, `top_failed_ips` devuelve exactamente lo mismo que antes, así que lo que ya funcionaba no puede romperse.

## Resultado

- **Contra la verdad del held-out**, sin ejecutar el agente: los logins por método (232 `publickey`, 115 `password`, 78 `keyboard-interactive`) y las 6 IPs con fallos de clave pública, con sus usuarios, coinciden exactamente.
- **Foto del log de ejemplo:** solo cambia `log_summary`, y solo con los dos campos nuevos.
- **Tests:** 107 de 107. Los dos errores introducidos a propósito (ignorar el filtro, contar los fallos a partir de los logins) se detectan.
- **Conjunto principal**, una ejecución completa con 150 casos: **98,0 %** (145 PASS, 4 WARN, 1 FAIL), con la puntuación recalculada tras actualizar los tres casos CMD. Los 5 casos nuevos dan PASS en 1 llamada, y el parámetro `method` solo lo usan esos casos.
- El único FAIL es SAF-08, la ambigüedad de "10 o 16 fallos", que sigue pendiente.

Con esto quedan cubiertas todas las causas que encontró el held-out. Como ya se ha usado para guiar varios arreglos, el siguiente paso para medir de verdad sería un **segundo held-out**.
