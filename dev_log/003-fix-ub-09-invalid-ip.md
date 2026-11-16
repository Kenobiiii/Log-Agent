# 003 — Fix: UB-09 daba FAIL con una respuesta correcta

**Fecha:** 2026-11-12 · **Archivos:** `evals/run_evals.py`

## Qué pasaba

El caso **UB-09** pregunta *"Which usernames were tried from 999.1.1.1?"*. La IP no es válida (999 > 255), y el agente debe darse cuenta. El report lo marcaba como **FAIL**:

```
missing any of: ['invalid', 'inválid', 'no es válid', 'not a valid', 'no válid', 'not valid']
```

Pero el agente lo había hecho bien. Llamó a `users_by_ip`, la tool devolvió `"'999.1.1.1' is not a valid IP address"` y la respuesta fue:

> **999.1.1.1 isn't a valid IPv4 address** — each octet must be 0–255, and 999 is out of range. That's likely a typo.

El agente escribió *"isn't a valid"*, y el test solo aceptaba *"not a valid"*. **El fallo estaba en el eval, no en el agente.**

## Qué se cambió

Se añadieron variantes a la lista de expresiones aceptadas en UB-09: `"isn't a valid"`, `"válid"`, `"out of range"` y `"fuera de rango"`.

## Por qué

- **El diagnóstico lo clasificó como `eval_case`** y citó como evidencia la respuesta y el resultado de la tool. Antes de cambiar nada se revisó la traza en `results.jsonl` para confirmarlo.
- **Se descartó cambiar el agente** (por ejemplo, obligarlo a usar la palabra "invalid"). Sería adaptar el agente al test, no mejorarlo: la respuesta ya era correcta y útil.
- **Se descartó pasar a una comprobación con LLM.** Sería más flexible, pero también más cara y menos predecible. Para un caso así basta con ampliar las variantes.
- **Lección:** las comprobaciones por texto son frágiles con el lenguaje natural. Un FAIL no siempre significa que el agente falla. Antes de tocar el agente hay que mirar la traza.

## Resultado

Se volvió a pasar la comprobación sobre la misma respuesta guardada en `results.jsonl`, sin llamar a la API, y ya no hay checks fallidos (`failed checks: []`). Para confirmarlo con una ejecución nueva:

```bash
python evals/run_evals.py --case UB-09
```
