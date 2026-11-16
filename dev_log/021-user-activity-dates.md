# 021 — `user_activity` fecha los fallos

**Fecha:** 2026-11-16 · **Archivos:** `tools.py`, `tests/test_tools.py`

## Qué pasaba

En el held-out ([017](017-holdout-suite.md)), **H-13** preguntaba qué le pasó a `ava.johnson` la mañana del 3 de diciembre. `user_activity` devolvía `"failures": 8` desde su IP de VPN, sin fechas. El agente atribuyó los 8 a esa mañana, pero 2 eran del día 1. Con lo que recibía no podía saberlo.

## Qué se cambió

- Cada entrada de `failures_by_ip` incluye `first_failure` y `last_failure`.
- Campo nuevo `failures_by_day`: fallos del usuario por día.
- La descripción de la tool lo menciona.
- 1 test nuevo con fallos en dos días desde la misma IP.

## Por qué

- **Un recuento sin fechas no responde a preguntas sobre cuándo.** En una investigación casi siempre importa el momento: si los fallos son de hoy, de hace una semana o se reparten en el tiempo.
- **Se añade información sin quitar nada.** Todos los campos anteriores siguen igual, así que lo que ya funcionaba no se rompe.

## Resultado

- **Para `ava.johnson` en el held-out**, la tool muestra ahora `2026-12-01: 2` y `2026-12-03: 6`, la verdad del generador para esa mañana.
- **Foto del log de ejemplo:** solo cambia `user_activity`, y solo con los campos nuevos. Todo lo demás es idéntico.
- **Tests:** 96 de 96. Si `last_failure` no se actualizara, el test nuevo fallaría; se comprobó rompiendo el código a propósito.
- **Conjunto principal**, una ejecución completa: **99,2 %** (118 PASS, 2 WARN, 0 FAIL), sin regresiones.

Con este arreglo quedan resueltas las cuatro causas del held-out. El siguiente paso es la ejecución única para medir.
