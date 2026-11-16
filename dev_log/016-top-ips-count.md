# 016 — `top_failed_ips` dice cuántas IPs devuelve (TF-12)

**Fecha:** 2026-11-16 · **Archivos:** `tools.py`, `tests/test_tools.py`

## Qué pasaba

En la ejecución *baseline* del 16-11 (`20261116-192033`, 96,2 %), el único FAIL fue **TF-12**: *"the top 10 attacking IPs with their counts, in a table"*. La tool devolvió 10 IPs, pero el agente escribió *"only 8 IPs returned"* y dejó la tabla con 8 filas.

Al repetir el caso 15 veces apareció un problema mayor que el FAIL. **En 13 de 15 respuestas, el agente afirmaba que la tool había devuelto menos IPs de las que devolvió** ("only 8 returned", "the tool's ranking has 8 entries"…), aunque casi siempre escribía las 10 filas. Solo en 1 de 15 perdía filas de verdad.

Es el mismo error que en [007](007-subnet-breakdown.md): **el modelo cuenta mal los elementos de una lista.** Además, `top_failed_ips` era la única tool que no indicaba cuántos elementos devolvía: `users_by_ip` tiene `distinct_users` y `success_after_failures` tiene `count`.

## Qué se cambió

- `top_failed_ips` devuelve un campo nuevo, `ips_returned`: el número de IPs de la lista.
- La descripción de la tool lo menciona.
- Un test unitario comprueba que `ips_returned` coincide siempre con la longitud de la lista.

## Por qué

- **Es la tercera vez que aparece el mismo principio:** si el modelo necesita un número, que lo calcule Python ([007](007-subnet-breakdown.md), [012](012-log-summary-description.md)).
- **No se tocó el prompt.** Pedirle al modelo que "cuente con cuidado" no lo hace fiable; darle el número, sí.
- **Coherencia entre tools.** Si todas las que devuelven listas dicen cuántos elementos tienen, el modelo no tiene que deducirlo en ningún caso.

## Resultado

TF-12, 15 ejecuciones por versión:

| | Sin `ips_returned` | Con `ips_returned` |
|---|---|---|
| FAIL (faltan filas) | 1 / 15 | 0 / 15 |
| Afirma un número de IPs falso | **13 / 15** | **0 / 15** |

Los 15 casos de `top_failed_ips`, comparados con la baseline: 93,3 % → **100 %**, sin regresiones.

**Lección:** el FAIL solo mostraba una parte del problema. Las respuestas con una afirmación falsa pero la tabla completa daban PASS, porque los checks buscan las IPs, no si lo que dice el texto es cierto. Repetir el caso y **leer las respuestas** mostró que el error era casi constante. Igual que con el idioma ([010](010-language-check.md)): **un PASS no significa que la respuesta sea correcta**, solo que pasa los checks que hemos escrito.
